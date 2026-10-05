from pathlib import Path

from config import Config
from media import sha256
from vbox import VBox


def unc(path):
    text = str(path)
    prefix = "/home/github-runner/"
    if not text.startswith(prefix):
        raise ValueError(f"cannot map to Windows UNC: {path}")
    suffix = text[len(prefix):].replace("/", "\\")
    return "\\\\wsl.localhost\\runner02\\home\\github-runner\\" + suffix


def reset_vm(oem_path, cfg=None, serial_path=None):
    cfg = cfg or Config()
    serial_path = Path(serial_path or (cfg.bench / "serial.log"))
    box = VBox(cfg)
    try:
        state = box.state()
        if state not in ("PoweredOff", "Saved", "AbortedSaved"):
            raise RuntimeError(
                f"refusing destructive reset while VM state is {state}"
            )

        if state in ("Saved", "AbortedSaved"):
            session = box.lock("Write")
            try:
                machine = box.session_machine(session)
                box._vals(
                    "IMachine_discardSavedState",
                    [("_this", machine), ("fRemoveFile", "true")],
                )
            finally:
                box.unlock(session)

        if box.state() != "PoweredOff":
            raise RuntimeError(f"cannot reset from {box.state()}")

        old_target = None
        for attachment in box.attachments():
            if (
                attachment["controller"] == "SATA"
                and attachment["port"] == 1
            ):
                old_target = attachment

        session = box.lock("Write")
        try:
            machine = box.session_machine(session)
            for port in (0, 1, 2, 3):
                try:
                    box._vals(
                        "IMachine_detachDevice",
                        [
                            ("_this", machine),
                            ("name", "SATA"),
                            ("controllerPort", str(port)),
                            ("device", "0"),
                        ],
                    )
                except Exception:
                    pass

            serial = box._vals(
                "IMachine_getSerialPort",
                [("_this", machine), ("slot", "0")],
            )[0]
            settings = [
                ("ISerialPort_setEnabled", "enabled", "true"),
                ("ISerialPort_setIOAddress", "IOAddress", "1016"),
                ("ISerialPort_setIRQ", "IRQ", "4"),
                ("ISerialPort_setUartType", "uartType", "U16550A"),
                (
                    "ISerialPort_setPath",
                    "path",
                    unc(serial_path),
                ),
                ("ISerialPort_setHostMode", "hostMode", "RawFile"),
            ]
            for operation, key, value in settings:
                box._vals(
                    operation,
                    [("_this", serial), (key, value)],
                )
            if cfg.vm_vcpus < 1:
                raise RuntimeError(f"invalid VM vCPU count: {cfg.vm_vcpus}")
            box._vals(
                "IMachine_setCPUCount",
                [("_this", machine), ("CPUCount", str(cfg.vm_vcpus))],
            )
            box.save_settings(machine)
        finally:
            box.unlock(session)

        if old_target and "bench" in old_target["location"]:
            try:
                progress = box._vals(
                    "IMedium_deleteStorage",
                    [("_this", old_target["medium"])],
                )[0]
                box.wait_progress(progress, 60000)
            except Exception:
                pass

        def create_vdi(path, size_gib, label):
            location = unc(path)
            box.close_hard_disks_at(location)
            if path.exists():
                path.unlink()
            disk = box._vals(
                "IVirtualBox_createMedium",
                [
                    ("_this", box.handle),
                    ("format", "VDI"),
                    ("location", location),
                    ("accessMode", "ReadWrite"),
                    ("aDeviceTypeType", "HardDisk"),
                ],
            )[0]
            progress = box._vals(
                "IMedium_createBaseStorage",
                [
                    ("_this", disk),
                    ("logicalSize", str(size_gib * 1024**3)),
                    ("variant", "Standard"),
                ],
            )[0]
            box.wait_progress(progress, 60000)
            error = box.progress_error(progress)
            if error:
                raise RuntimeError(f"{label} VDI creation failed: {error}")
            return disk

        guard = cfg.guard
        guard_medium = create_vdi(guard, cfg.guard_size_gib, "guard")
        target = cfg.vm_target_vdi
        medium = create_vdi(target, cfg.target_size_gib, "target")

        official = cfg.cache / (
            "tumbleweed-dvd/"
            "openSUSE-Tumbleweed-DVD-x86_64-"
            "Snapshot20260930-Media.iso"
        )
        base = box._vals(
            "IVirtualBox_openMedium",
            [
                ("_this", box.handle),
                ("location", unc(official)),
                ("deviceType", "DVD"),
                ("accessMode", "ReadOnly"),
                ("forceNewUuid", "false"),
            ],
        )[0]
        oem = box._vals(
            "IVirtualBox_openMedium",
            [
                ("_this", box.handle),
                ("location", unc(Path(oem_path))),
                ("deviceType", "DVD"),
                ("accessMode", "ReadOnly"),
                ("forceNewUuid", "false"),
            ],
        )[0]
        session = box.lock("Write")
        try:
            machine = box.session_machine(session)
            attachments = [
                (0, "HardDisk", guard_medium),
                (1, "HardDisk", medium),
                (2, "DVD", base),
                (3, "DVD", oem),
            ]
            for port, device_type, attached in attachments:
                box._vals(
                    "IMachine_attachDevice",
                    [
                        ("_this", machine),
                        ("name", "SATA"),
                        ("controllerPort", str(port)),
                        ("device", "0"),
                        ("type", device_type),
                        ("medium", attached),
                    ],
                )

            for slot in range(4):
                adapter = box._vals(
                    "IMachine_getNetworkAdapter",
                    [("_this", machine), ("slot", str(slot))],
                )[0]
                box._vals(
                    "INetworkAdapter_setEnabled",
                    [("_this", adapter), ("enabled", "false")],
                )
            box.save_settings(machine)
        finally:
            box.unlock(session)

        serial_path.parent.mkdir(parents=True, exist_ok=True)
        if serial_path.exists():
            serial_path.unlink()

        baseline = sha256(target)
        (cfg.bench / "target.clean.sha256").write_text(
            f"{baseline}  {target}\n"
        )
        return {
            "target": target,
            "baseline_sha256": baseline,
            "oem": Path(oem_path),
        }
    finally:
        box.logoff()
