import json
import os
import time
from pathlib import Path

from boot import boot_installer
from capture import screenshot, serial_text
from config import Config
from keyboard import Keyboard
from logstream import enable_y2log
from machine import reset_vm
from media import build_oemdrv, sha256
from vbox import VBox


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


def start(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    session = None
    try:
        session = boot_installer(box)
        print("BOOTED_INSTALLER", flush=True)
        while box.state() == "Running":
            time.sleep(2)
        print("VM_STATE", box.state(), flush=True)
    finally:
        if session:
            try:
                box.unlock(session)
            except Exception:
                pass
        box.logoff()


def fill(name, cfg=None):
    cfg = cfg or Config()
    if name not in ("recovery", "pin", "root"):
        raise ValueError(name)
    box = VBox(cfg)
    try:
        Keyboard(box).fill(name, cfg, trace=True)
        time.sleep(1)
        path = cfg.bench / f"after-{name}.png"
        screenshot(box, path)
        return str(path)
    finally:
        box.logoff()


def logs(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        enable_y2log(box)
        time.sleep(1)
        path = cfg.bench / "after-y2log.png"
        screenshot(box, path)
        return str(path)
    finally:
        box.logoff()


def shot(name="latest", cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        path = cfg.bench / f"{name}.png"
        screenshot(box, path)
        return str(path)
    finally:
        box.logoff()


def status(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        target = cfg.bench / "target.vdi"
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
            "serial_tail": "\n".join(
                serial_text(cfg).splitlines()[-40:]
            ),
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
