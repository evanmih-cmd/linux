from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from config import Config
from invariants import validate_profile_storage, validate_source_tree
from media import (
    load_credentials,
    render_runtime_profile,
    sha256,
    verify_patchset_against_snapshot,
)
from rawserial import clean_text
from vbox import VBox


YAST_NS = "http://www.suse.com/1.0/yast2ns"


def latest_serial_path(cfg):
    runs = [p for p in cfg.runs.iterdir() if p.is_dir()] if cfg.runs.exists() else []
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for run in runs:
        path = run / "serial.log"
        if path.exists():
            return path
    return None


def _runtime_credential_state(profile_path):
    ns = {"y": YAST_NS}
    root = ET.parse(profile_path).getroot()

    asks = root.find("y:general/y:ask-list", ns)
    remaining = []
    if asks is not None:
        for ask in list(asks):
            title = ask.find("y:title", ns)
            path = ask.find("y:path", ns)
            title_text = "" if title is None else (title.text or "")
            path_text = "" if path is None else (path.text or "")
            if path_text == "partitioning,0,partitions,1,crypt_key":
                remaining.append("recovery")
            elif path_text == "users,0,user_password":
                remaining.append("root")
            elif title_text == "Portable workstation TPM credential":
                remaining.append("pin")
            else:
                raise RuntimeError(
                    "unexpected AutoYaST ask remains in runtime profile: "
                    f"title={title_text!r} path={path_text!r}"
                )

    crypt_key = root.find(
        "y:partitioning/y:drive/y:partitions/y:partition[2]/y:crypt_key",
        ns,
    )
    root_password = root.find("y:users/y:user/y:user_password", ns)
    pre_source = root.find("y:scripts/y:pre-scripts/y:script/y:source", ns)

    return {
        "remaining": remaining,
        "recovery_placeholder": (
            crypt_key is None or (crypt_key.text or "") == "__ASK__"
        ),
        "root_placeholder": (
            root_password is None or (root_password.text or "") == "__ASK__"
        ),
        "pin_file_reference": "/etc/desktop-linux-tpm2-pin" in Path(profile_path).read_text(),
        "profile_ready_marker": (
            pre_source is not None
            and "VMBENCH_PROFILE_READY" in (pre_source.text or "")
        ),
    }


def _check_runtime_profile(cfg, credentials):
    expected_missing = [
        key for key in ("recovery", "pin", "root") if key not in credentials
    ]
    with TemporaryDirectory() as td:
        runtime = Path(td) / "autoinst.xml"
        mode = render_runtime_profile(cfg, runtime, credentials)
        state = _runtime_credential_state(runtime)

    if sorted(mode["missing"]) != sorted(expected_missing):
        raise RuntimeError(
            f"credential mode mismatch: {mode['missing']} != {expected_missing}"
        )
    if sorted(state["remaining"]) != sorted(expected_missing):
        raise RuntimeError(
            f"runtime prompts mismatch: {state['remaining']} != {expected_missing}"
        )

    if ("recovery" in credentials) == state["recovery_placeholder"]:
        raise RuntimeError("runtime recovery credential embedding mismatch")
    if ("root" in credentials) == state["root_placeholder"]:
        raise RuntimeError("runtime root credential embedding mismatch")
    if not state["profile_ready_marker"]:
        raise RuntimeError("runtime profile-ready marker missing")
    expected_pin_reference = "pin" not in credentials
    if state["pin_file_reference"] != expected_pin_reference:
        raise RuntimeError(
            "runtime TPM PIN handoff mismatch: interactive ask must write the "
            "installation-system path, embedded DUD mode must not need a pre-script bridge"
        )

    return mode


def static_check(cfg=None):
    cfg = cfg or Config()
    harness_root = Path(__file__).resolve().parent
    validate_source_tree(harness_root)
    validate_profile_storage(cfg.profile)
    patch_proof = verify_patchset_against_snapshot(cfg)

    actual = load_credentials(cfg)
    actual_mode = _check_runtime_profile(cfg, actual)

    dummy = {
        "recovery": "vmbench-recovery-test-only",
        "pin": "123456",
        "root": "vmbench-root-test-only",
    }
    keys = ("recovery", "pin", "root")
    matrix = []
    for mask in range(8):
        creds = {
            key: dummy[key]
            for bit, key in enumerate(keys)
            if mask & (1 << bit)
        }
        mode = _check_runtime_profile(cfg, creds)
        matrix.append(
            {
                "embedded": mode["embedded"],
                "missing": mode["missing"],
            }
        )

    return {
        "status": "PASS",
        "vm_touched": False,
        "profile_sha256": sha256(cfg.profile),
        "actual_credentials": {
            "embedded": actual_mode["embedded"],
            "missing": actual_mode["missing"],
        },
        "credential_matrix_cases": len(matrix),
        "source_invariants": "PASS",
        "storage_profile_invariant": "PASS",
        "patchset_applicability": "PASS",
        "patches": patch_proof["patches"],
        "post_patch_hashes": patch_proof["post_patch_hashes"],
    }


def status(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        target = cfg.bench / "target.vdi"
        serial = latest_serial_path(cfg)
        serial_tail = ""
        if serial and serial.exists():
            serial_tail = clean_text(serial.read_bytes())[-40000:]
        result = {
            "vm_state": box.state(),
            "session_state": box.session_state(),
            "target_exists": target.exists(),
            "target_allocated": (
                target.stat().st_blocks * 512 if target.exists() else 0
            ),
            "target_sha256": sha256(target) if target.exists() else None,
            "baseline_sha256": None,
            "vbox_log_folder": box.log_folder(),
            "serial_config": box.serial_config(),
            "serial_path": str(serial) if serial else None,
            "serial_tail": "\n".join(serial_tail.splitlines()[-80:]),
        }
        baseline = cfg.bench / "target.clean.sha256"
        if baseline.exists():
            result["baseline_sha256"] = baseline.read_text().split()[0]
        return result
    finally:
        box.logoff()
