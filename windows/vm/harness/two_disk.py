"""Separate disposable two-disk Windows 11 Setup bench.

No operations here target the existing Desktop-Windows-11-Pro VM.
The exact same answer renderer runs in both environments. WinPE Offline
and Setup's destination selection must be performed by the human operator.
"""
import json
from dataclasses import replace
from pathlib import Path

from answer import attach_install_media
from config import Config
from machine import VM_MARKER, unc
from media import verify_official_iso
from protected_gpt import initialize_protected_medium, verify_protected_medium
from runner import start_vm
from vbox import VBox, VBoxError

DISK_SIZE_GIB = 8
TARGET_SIZE_GIB = 96
VM_SUFFIX = "-TwoDisk"
CACHE_SUFFIX = "-two-disk"
STATE_FILE = "protected-ssd1.json"
PROTECTED_DISK = "protected-home.vdi"


def dual_config(cfg=None):
    cfg = cfg or Config()
    name = cfg.vm_name + VM_SUFFIX
    if VM_SUFFIX in cfg.vm_name or name == "Desktop-Windows-11-Pro":
        raise ValueError("invalid isolated two-disk VM name")
    # Do NOT reuse the canonical VM disk/credentials/cache/snapshots.
    return replace(
        cfg,
        vm_name=name,
        cache=cfg.cache.with_name(cfg.cache.name + CACHE_SUFFIX),
        vm_disk_gib=TARGET_SIZE_GIB,
    )


def _state_path(cfg):
    return cfg.bench / STATE_FILE


def _protected_path(cfg):
    return cfg.bench / PROTECTED_DISK


def _load_protection(cfg):
    path = _state_path(cfg)
    if not path.is_file():
        raise RuntimeError("two-disk sentinel manifest missing")
    return json.loads(path.read_text())


def prepare(cfg=None):
    cfg = dual_config(cfg)
    source = verify_official_iso(cfg)
    protected_path = _protected_path(cfg)
    if _state_path(cfg).exists():
        raise RuntimeError("two-disk bench already prepared; refusing overwrite")
    box = VBox(cfg)
    try:
        if box.machine:
            # Recover only our fresh, controllerless, still-unconfigured VM
            # created during a failed initial preparation. Never reset it.
            if (box.state() != "PoweredOff" or box.description()
                    or box._vals("IMachine_getStorageControllers",
                                 [("_this", box.machine)])):
                raise VBoxError("existing two-disk VM is not an empty staging VM")
            if not protected_path.is_file() or not cfg.vm_disk.is_file():
                raise RuntimeError("partial two-disk VDI set is incomplete")
            protected = box._vals(
                "IVirtualBox_openMedium",
                [("_this", box.handle), ("location", unc(protected_path)),
                 ("deviceType", "HardDisk"), ("accessMode", "ReadWrite"),
                 ("forceNewUuid", "false")],
            )[0]
            target = box._vals(
                "IVirtualBox_openMedium",
                [("_this", box.handle), ("location", unc(cfg.vm_disk)),
                 ("deviceType", "HardDisk"), ("accessMode", "ReadWrite"),
                 ("forceNewUuid", "false")],
            )[0]
        else:
            if cfg.vm_disk.exists() or protected_path.exists():
                raise RuntimeError("two-disk VDI path occupied; refusing overwrite")
            cfg.bench.mkdir(parents=True, exist_ok=True)
            box.create_machine(cfg.vm_name)
            protected = box.create_medium(
                unc(protected_path), DISK_SIZE_GIB*1024**3
            )
            target = box.create_medium(
                unc(cfg.vm_disk), TARGET_SIZE_GIB*1024**3
            )
        marker = initialize_protected_medium(box, protected, DISK_SIZE_GIB*1024**3)
        box.configure_windows_hardware(target, disk_port=1)
        box.attach_hard_disk(protected, port=0)
        info = {
            **marker,
            "vm": cfg.vm_name,
            "protected_disk": str(protected_path),
            "target_disk": str(cfg.vm_disk),
            "protected_port": 0,
            "target_port": 1,
            "protected_gib": DISK_SIZE_GIB,
            "target_gib": TARGET_SIZE_GIB,
            "installation_media_sha256": cfg.official_iso_sha256,
            "partitioning": "Windows Setup stock defaults on manually chosen target",
            "stage": "disks-created",
            "release_approval": False,
        }
        _state_path(cfg).write_text(json.dumps(info, indent=2)+"\n")
    finally:
        box.logoff()

    # No environment-specific XML differences: only the SOAP DVD ports differ.
    media = attach_install_media(cfg, ports=(3, 4, 5))
    return {
        "status": "PASS",
        "stage": "prepared",
        "vm": cfg.vm_name,
        "protected_disk": str(protected_path),
        "target_disk": str(cfg.vm_disk),
        "protected_port": 0,
        "target_port": 1,
        "answer_contract": media["xml_contract_status"],
        "source": source,
        "manual_selection_required": True,
        "guest_additions_installation": "post-Setup bench-only manual step",
    }


def _verification(cfg, box):
    info = _load_protection(cfg)
    if box.state() != "PoweredOff":
        raise VBoxError("physical VDI sentinel inspection requires PoweredOff VM")
    protected = box._vals(
        "IMachine_getMedium",
        [("_this", box.machine), ("name", "SATA"),
         ("controllerPort", "0"), ("device", "0")],
    )[0]
    result = verify_protected_medium(box, protected, info)
    result["vm"] = cfg.vm_name
    result["stage"] = "sentinel-verification"
    result["release_approval"] = False
    return result


def status(cfg=None, *, verify=False):
    cfg = dual_config(cfg)
    box = VBox(cfg)
    try:
        if not box.machine:
            return {"registered": False, "vm": cfg.vm_name}
        out = {
            "vm": cfg.vm_name,
            "registered": True,
            "state": box.state(),
            "session_state": box.session_state(),
            "harness_owned": VM_MARKER in box.description(),
            "protected_disk_exists": _protected_path(cfg).is_file(),
            "target_disk_exists": cfg.vm_disk.is_file(),
            "sentinel_manifest_exists": _state_path(cfg).is_file(),
        }
        if verify:
            out["sentinel"] = _verification(cfg, box)
            out["status"] = out["sentinel"]["status"]
        if box.state() == "Running":
            out["framebuffer"] = box.framebuffer_evidence()
        return out
    finally:
        box.logoff()


def boot(cfg=None):
    cfg = dual_config(cfg)
    box = VBox(cfg, require_machine=True)
    try:
        if VM_MARKER not in box.description():
            raise VBoxError("two-disk VM not owned by harness")
        if box.state() != "PoweredOff":
            raise VBoxError("two-disk boot requires PoweredOff VM")
        sentinel = _verification(cfg, box)
        if sentinel["status"] != "PASS":
            raise VBoxError("protected disk sentinel invalid: refusing boot")
    finally:
        box.logoff()
    result = start_vm(cfg, accept_optical_boot=True)
    return {
        "status": "PASS",
        "vm": cfg.vm_name,
        "stage": "manual-winpe-offline-and-setup-target-selection",
        "boot": result,
        "protected_disk": "SATA port 0, 8 GiB, Home-like GPT + sentinel",
        "target_disk": "SATA port 1, 96 GiB, blank LUN",
        "manual_steps": [
            "Shift+F10 to WinPE DiskPart",
            "list disk; select disk after identifying protected 8 GiB SSD1",
            "detail disk; offline disk; detail disk (verify Offline)",
            "return to Setup and select only the 96 GiB LUN Unallocated Space",
            "Next; stock Setup partitions and proceeds with common XML",
        ],
        "no_guest_gui_injection": True,
        "physical_acceptance": "BLOCKED_UNTIL_LIVE_TWO_DISK_PROOF",
    }
