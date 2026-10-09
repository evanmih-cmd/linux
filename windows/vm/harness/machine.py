from pathlib import Path

from config import Config
from media import verify_official_iso
from vbox import VBox, VBoxError


VM_MARKER = "Managed by windows/vm/harness (#6)"


def unc(path):
    """Map the runner WSL path into the path visible to Windows vboxwebsrv."""
    text = str(Path(path).resolve())
    prefix = "/home/github-runner/"
    if not text.startswith(prefix):
        raise ValueError(f"cannot map path to Windows UNC: {path}")
    suffix = text[len(prefix):].replace("/", "\\")
    return "\\\\wsl.localhost\\runner02\\home\\github-runner\\" + suffix


def _safe_unlink_bench_disk(cfg):
    path = cfg.vm_disk.resolve()
    bench = cfg.bench.resolve()
    if bench not in path.parents or path.name != "windows11-pro.vdi":
        raise RuntimeError(f"refusing to delete unexpected disk path: {path}")
    path.unlink(missing_ok=True)


def reset_vm(cfg=None):
    """Destroy/recreate only the canonical harness-owned Windows VM."""
    cfg = cfg or Config()
    cfg.bench.mkdir(parents=True, exist_ok=True)
    cfg.runs.mkdir(parents=True, exist_ok=True)
    iso = verify_official_iso(cfg)

    box = VBox(cfg)
    try:
        if box.machine:
            if VM_MARKER not in box.description():
                raise VBoxError(
                    f"refusing to delete VM {cfg.vm_name!r}: "
                    "it is not marked as harness-owned"
                )
            box.unregister_and_delete()

        _safe_unlink_bench_disk(cfg)

        box.create_machine(cfg.vm_name, os_type="Windows11_64")
        disk = box.create_medium(
            unc(cfg.vm_disk),
            cfg.vm_disk_gib * 1024**3,
        )
        hardware = box.configure_windows_hardware(disk)

        return {
            "status": "PASS",
            "vm": cfg.vm_name,
            "disk": str(cfg.vm_disk),
            "disk_gib": cfg.vm_disk_gib,
            "memory_mib": cfg.vm_memory_mib,
            "vcpus": cfg.vm_vcpus,
            "firmware": box.firmware_type(),
            "tpm": box.tpm_type(),
            "secure_boot": box.secure_boot_enabled(),
            "keyboard_hid": box.keyboard_hid_type(),
            "graphics": box.graphics_config(),
            "network": box.network_config(),
            "nested_hwvirt_requested": cfg.vm_nested_hwvirt,
            "nested_hwvirt_configured": hardware["nested_hwvirt"],
            "iso": iso,
        }
    finally:
        box.logoff()


def vm_status(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        if not box.machine:
            return {
                "registered": False,
                "vm": cfg.vm_name,
            }
        owned = VM_MARKER in box.description()
        result = {
            "registered": True,
            "owned_by_harness": owned,
            "vm": cfg.vm_name,
            "state": box.state(),
            "session_state": box.session_state(),
            "firmware": box.firmware_type(),
            "tpm": box.tpm_type(),
            "secure_boot": box.secure_boot_enabled(),
            "keyboard_hid": box.keyboard_hid_type(),
            "graphics": box.graphics_config(),
            "network": box.network_config(),
            "disk_exists": cfg.vm_disk.exists(),
        }
        if box.state() in ("Running", "Paused"):
            try:
                result["guest_additions_run_level"] = (
                    box.guest_additions_run_level()
                )
            except Exception as exc:
                result["guest_additions_error"] = repr(exc)
        return result
    finally:
        box.logoff()


def destroy_vm(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        if not box.machine:
            _safe_unlink_bench_disk(cfg)
            return {"status": "PASS", "deleted": False}
        if VM_MARKER not in box.description():
            raise VBoxError(
                f"refusing to delete VM {cfg.vm_name!r}: "
                "it is not marked as harness-owned"
            )
        box.unregister_and_delete()
        _safe_unlink_bench_disk(cfg)
        return {"status": "PASS", "deleted": True}
    finally:
        box.logoff()
