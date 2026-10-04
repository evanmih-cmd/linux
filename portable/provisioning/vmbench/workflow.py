from config import Config
from machine import reset_vm
from media import build_oemdrv, sha256
from rawserial import clean_text
from vbox import VBox


def latest_serial_path(cfg):
    runs = [p for p in cfg.runs.iterdir() if p.is_dir()] if cfg.runs.exists() else []
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for run in runs:
        path = run / "serial.log"
        if path.exists():
            return path
    return None


def prepare(cfg=None):
    cfg = cfg or Config()
    built = build_oemdrv(cfg)
    reset = reset_vm(built["iso"], cfg)
    return {
        "build": {
            "id": built["id"],
            "iso": str(built["iso"]),
            "profile_sha": built["profile_sha"],
            "patch_sha": built["patch_sha"],
        },
        "reset": {
            "target": str(reset["target"]),
            "baseline_sha256": reset["baseline_sha256"],
            "oem": str(reset["oem"]),
        },
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


def stop(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        box.poweroff()
        return box.state()
    finally:
        box.logoff()
