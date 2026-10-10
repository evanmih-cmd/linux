"""One-shot installed-Windows audit of an existing running VM.

No Guest Control, guest password, guest account, disk changes or
alternate audit policy. Stock audit.ps1 runs in an existing elevated console;
VBoxControl Guest Properties transfer its JSON to the host for audit.evaluate().
"""
import argparse
import base64
import fcntl
import gzip
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from audit import evaluate
from config import Config
from machine import unc
from vbox import VBox

DRIVE = "F"
SATA_PORT = 4
PREFIX = "/desktopwindows/liveaudit"
CHAR_KEYS = dict(zip(
    "abcdefghijklmnopqrstuvwxyz",
    (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25,
     16, 19, 31, 20, 22, 47, 17, 45, 21, 44),
))
CHAR_KEYS.update({":": 39, "\\": 43, ".": 52, " ": 57, "/": 53})
CHAR_KEYS.update(dict(zip("1234567890", range(2, 12))))


def build_media(cfg, run_dir, run_id):
    media = run_dir / "media"
    media.mkdir()
    shutil.copyfile(cfg.audit_script, media / "AUDIT.PS1")
    payload = cfg.payload
    shutil.copyfile(payload / "run-audit.ps1", media / "RUN-AUDIT.PS1")
    shutil.copyfile(payload / "evaluate-audit.ps1", media / "EVALUATE-AUDIT.PS1")
    shutil.copyfile(Path(__file__).with_name("guest_audit_publish.ps1"), media / "PUBLISH.PS1")
    (media / "RUN.CMD").write_bytes((
        "@echo off\r\n"
        "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f'-File "%~dp0PUBLISH.PS1" -RunId {run_id} -AuditPath "%~dp0RUN-AUDIT.PS1"\r\n'
        "exit /b %errorlevel%\r\n"
    ).encode("ascii"))
    iso = run_dir / "audit.iso"
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(cfg.xorriso_lib)
    subprocess.run(
        [str(cfg.xorriso), "-as", "mkisofs", "-quiet", "-J", "-joliet-long",
         "-V", "WINAUDIT", "-o", str(iso), str(media)],
        check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if iso.stat().st_size < 1024:
        raise RuntimeError("Audit ISO is unexpectedly small")
    return iso


def guest_property(box, key):
    values = box._vals(
        "IMachine_getGuestPropertyValue",
        [("_this", box.machine), ("property", key)],
    )
    return values[0] if values else ""


def receive_facts(box, run_id, timeout):
    path = f"{PREFIX}/{run_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = guest_property(box, f"{path}/state")
        if state == "failed":
            raise RuntimeError("Windows audit failed: " +
                               guest_property(box, f"{path}/error"))
        if state == "ready":
            count_text = guest_property(box, f"{path}/count")
            if not count_text.isdecimal():
                raise RuntimeError("Malformed report chunk count")
            count = int(count_text)
            if not 1 <= count <= 120:
                raise RuntimeError("Report chunk count out of bounds")
            encoded = "".join(guest_property(box, f"{path}/part{i:03}") for i in range(count))
            raw = gzip.decompress(base64.b64decode(encoded, validate=True))
            if not 1 <= len(raw) <= 1048576:
                raise RuntimeError("Report has invalid length")
            expected = guest_property(box, f"{path}/sha256")
            if hashlib.sha256(raw).hexdigest() != expected:
                raise RuntimeError("Report checksum mismatch")
            return json.loads(raw.decode("utf-8-sig")), raw
        if box.state() != "Running":
            raise RuntimeError("Windows VM stopped during audit")
        time.sleep(2)
    raise TimeoutError(
        f"Windows audit result not received within {timeout}s. "
        "The VM might not have received the keyboard command, "
        "or the guest audit is still running. Do not interpret as an OS failure."
    )


def type_one_command(box, command, *, open_run_dialog=False):
    """Inject only a bounded, single stock Windows command via existing SOAP."""
    if len(command) > 100 or any(char.lower() not in CHAR_KEYS for char in command):
        raise ValueError("Audit command contains unsupported keyboard character")
    session = box.lock("Shared")
    try:
        console = box.session_console(session)
        keyboard = box._vals("IConsole_getKeyboard", [("_this", console)])[0]
        box.call("IKeyboard_releaseKeys", [("_this", keyboard)])
        def send(codes):
            accepted = box._vals(
                "IKeyboard_putScancodes",
                [("_this", keyboard)] + [("scancodes", str(value)) for value in codes],
            )
            if accepted != [str(len(codes))]:
                raise RuntimeError("SOAP did not accept full key sequence")
        if open_run_dialog:
            send([0xe0, 0x5b, 0x13, 0x93, 0xe0, 0xdb])
            time.sleep(1)
        for char in command:
            code = CHAR_KEYS[char.lower()]
            codes = (
                [42, code, code | 128, 170]
                if char.isupper() or char == ":" else [code, code | 128]
            )
            send(codes)
            time.sleep(.12)
        send([28, 156])
    finally:
        box.unlock(session)


def mount_media(box, iso, port=SATA_PORT):
    handle = box._vals("IVirtualBox_openMedium", [
        ("_this", box.handle), ("location", unc(iso)),
        ("deviceType", "DVD"), ("accessMode", "ReadOnly"),
        ("forceNewUuid", "false"),
    ])[0]
    session = box.lock("Shared")
    try:
        machine = box.session_machine(session)
        original = box._vals("IMachine_getMedium", [
            ("_this", machine), ("name", "SATA"),
            ("controllerPort", str(port)), ("device", "0"),
        ])[0]
        box._vals("IMachine_mountMedium", [
            ("_this", machine), ("name", "SATA"),
            ("controllerPort", str(port)), ("device", "0"),
            ("medium", handle), ("force", "false"),
        ])
        return original
    finally:
        box.unlock(session)


def restore_media(box, original, port=SATA_PORT):
    session = box.lock("Shared")
    try:
        machine = box.session_machine(session)
        box._vals("IMachine_mountMedium", [
            ("_this", machine), ("name", "SATA"),
            ("controllerPort", str(port)), ("device", "0"),
            ("medium", original), ("force", "false"),
        ])
    finally:
        box.unlock(session)


def run(cfg, *, timeout=240, drive=DRIVE):
    # Audit the CURRENT installation, not the old one-disk benchmark.
    if cfg.vm_name != "Desktop-Windows-11-Pro-TwoDisk":
        raise RuntimeError("Explicitly select Desktop-Windows-11-Pro-TwoDisk")
    if drive not in ("F", "G", "H", "I"):
        raise RuntimeError("Unexpected optical letter")
    run_id = secrets.token_hex(6)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = cfg.cache / "live-audit" / f"{stamp}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    iso = build_media(cfg, run_dir, run_id)
    print("RUN", run_dir, flush=True)
    box = VBox(cfg, require_machine=True)
    restored = False
    try:
        if box.state() != "Running" or box.guest_additions_run_level() != "Desktop":
            raise RuntimeError("Requires existing running Windows with Guest Additions Desktop")
        original = mount_media(box, iso)
        try:
            # Single trigger. The precondition is an open elevated cmd.exe in
            # this disposable VM, as confirmed by an actual console screenshot.
            command = f"{drive}:\\RUN.CMD"
            print("WINDOWS_COMMAND", command, flush=True)
            type_one_command(box, command, open_run_dialog=True)
            facts, raw = receive_facts(box, run_id, timeout)
            (run_dir / "facts.json").write_bytes(raw)
            result = evaluate(facts)
            (run_dir / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            counts = {
                state: sum(item["status"] == state for item in result["checks"])
                for state in ("PASS", "FAIL", "NOT_PROVABLE_IN_VM", "WARN")
            }
            print("AUDIT", json.dumps({"status": result["status"], "counts": counts,
                                        "failed": result["failed"], "run": str(run_dir)}),
                  flush=True)
            restored = True
            return result
        finally:
            if restored:
                restore_media(box, original)
            else:
                print("NOTE: audit ISO remains mounted for investigation; "
                      "no reset/reboot was attempted.", flush=True)
    finally:
        box.logoff()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--drive", default=DRIVE)
    parser.add_argument("--evaluate", type=Path,
                        help="evaluate a previously received facts.json; no VM actions")
    args = parser.parse_args()
    if args.evaluate:
        result = evaluate(json.loads(args.evaluate.read_text(encoding="utf-8-sig")))
        print(json.dumps({"status": result["status"], "failed": result["failed"]},
                         indent=2))
        raise SystemExit(1 if result["failed"] else 0)
    if args.timeout < 5 or args.timeout > 3600:
        parser.error("timeout outside 5..3600 seconds")
    cfg = Config()
    lock = cfg.cache / "live-audit" / ".controller.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        outcome = run(cfg, timeout=args.timeout, drive=args.drive.upper())
    raise SystemExit(1 if outcome["failed"] else 0)


if __name__ == "__main__":
    main()
