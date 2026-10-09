"""Run read-only Windows guest audit through existing *temporary* elevated access.

This is VM controller transport, not a desired-state config script. The
existing elevated interactive Task Scheduler entry is preserved, not removed,
and its original launcher is restored even if auditing fails. Nothing from
this access path is part of physical ASUS production installer artifacts.
"""
import json
import secrets
import tempfile
import time
from pathlib import Path, PureWindowsPath

from config import Config
from guest import GuestControl
from media import load_or_create_credentials
from vbox import VBox

TASK = "DesktopWindows-Configure-Elevated"
LAUNCHER = "run-configuration-interactive.cmd"


def capture_elevated_facts(cfg=None, out_dir=None):
    cfg = cfg or Config()
    out_dir = Path(out_dir or (cfg.cache / "guest-diag" / "elevated-audit"))
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg.bench.mkdir(parents=True, exist_ok=True)
    credentials = load_or_create_credentials(cfg)
    original = cfg.repo / "windows/vm/harness" / LAUNCHER
    if not original.is_file():
        raise FileNotFoundError(f"expected VM launcher missing: {original}")

    # Per-run unique names prevent stale success results from previous runs.
    run_id = secrets.token_hex(8)
    prefix = f"elevated-audit-{run_id}"
    guest_dir = PureWindowsPath(cfg.guest_work_dir)
    json_path = str(guest_dir / (prefix + ".json"))
    rc_path = str(guest_dir / (prefix + ".rc"))
    log_path = str(guest_dir / (prefix + ".log"))
    launcher_text = (
        "@echo off\r\n"
        f'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass '
        f'-File "{guest_dir}\\audit.ps1" -OutputPath "{json_path}" '
        f'> "{log_path}" 2>&1\r\n'
        "set RC=%ERRORLEVEL%\r\n"
        f'> "{rc_path}" echo %RC%\r\n'
        "exit /b %RC%\r\n"
    )

    box = VBox(cfg, require_machine=True)
    try:
        if box.state() != "Running":
            raise RuntimeError(f"cannot audit VM state={box.state()}")
        with GuestControl(box, credentials["user"], credentials["password"]) as guest:
            guest.ensure_directory(cfg.guest_work_dir)
            guest.copy_to_guest(cfg.audit_script, cfg.guest_work_dir)
            try:
                with tempfile.TemporaryDirectory(prefix="elevated-audit-", dir=cfg.bench) as tmp:
                    launcher = Path(tmp) / LAUNCHER
                    launcher.write_bytes(launcher_text.encode("utf-8"))
                    guest.copy_to_guest(launcher, cfg.guest_work_dir)

                    # Refuse a different task or a legacy/non-elevated principal.
                    start = (
                        f"$t=Get-ScheduledTask -TaskName '{TASK}' -ErrorAction Stop;"
                        "if($t.State -ne 'Ready' -or "
                        "$t.Principal.RunLevel -ne 'Highest' -or "
                        "$t.Principal.LogonType -ne 'Interactive' -or "
                        "$t.Actions.Count -ne 1 -or "
                        "$t.Actions[0].Execute -ne 'C:\\Windows\\System32\\cmd.exe' -or "
                        f"$t.Actions[0].Arguments -notlike '*{LAUNCHER}*')"
                        "{throw 'Elevation task contract violation'};"
                        f"Start-ScheduledTask -TaskName '{TASK}' -ErrorAction Stop"
                    )
                    guest.powershell(start, timeout_ms=60000)

                    deadline = time.monotonic() + 240
                    exit_code = None
                    while time.monotonic() < deadline:
                        try:
                            rc_file = guest.copy_from_guest(rc_path, out_dir)
                            exit_code = int(rc_file.read_text().strip())
                            break
                        except Exception:
                            time.sleep(3)
                    if exit_code is None:
                        raise TimeoutError("elevated guest audit did not complete within 240s")

                    if exit_code != 0:
                        try:
                            guest.copy_from_guest(log_path, out_dir)
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"read-only guest audit returned {exit_code}; check captured log"
                        )

                    data_file = guest.copy_from_guest(json_path, out_dir)
                    facts = json.loads(data_file.read_text(encoding="utf-8-sig"))
                    if facts.get("AuditContext", {}).get("IsElevated") is not True:
                        raise RuntimeError("audit ran without actual administrator elevation")
                    if (facts["AuditContext"].get("User", "").casefold()
                            != f"{cfg.guest_hostname}\\{credentials['user']}".casefold()):
                        raise RuntimeError("audit ran in an unexpected Windows identity")
                    # Stable artifact consumed by audit.py, never include secrets.
                    stable_file = out_dir / "audit.json"
                    stable_file.write_text(
                        json.dumps(facts, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8"
                    )
                    return facts
            finally:
                # Restore canonical WinGet task launcher for subsequent test runs.
                guest.copy_to_guest(original, cfg.guest_work_dir)
    finally:
        box.logoff()


if __name__ == "__main__":
    facts = capture_elevated_facts()
    print(json.dumps({
        "IsElevated": facts["AuditContext"]["IsElevated"],
        "SecureBoot": facts["SecureBoot"],
        "TPM": facts["TPM"],
        "WinRE": facts["WinRE"],
        "BitLocker": facts["BitLocker"],
        "AdministratorProtection": facts["AdministratorProtection"],
    }, indent=2, ensure_ascii=False))
