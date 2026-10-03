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
    return r"\\wsl.localhost\runner02\home\github-runner\" + suffix


def reset_vm(oem_path, cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        box.poweroff()

        if box.state() in ("Saved", "AbortedSaved"):
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
            for port in (1, 2, 3):
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
                    unc(cfg.bench / "serial.log"),
                ),
                ("ISerialPort_setHostMode", "hostMode", "RawFile"),
            ]
            for operation, key, value in settings:
                box._vals(
                    operation,
                    [("_this", serial), (key, value)],
                )
            box.save_settings(machine)
        finally:
            box.unlock(session)

        if (
            old_target
            and (
                old_target["location"].endswith("bench\\target.vdi")
                or old_target["location"].endswith("bench/target.vdi")
            )
        ):
            try:
                progress = box._vals(
                    "IMedium_deleteStorage",
                    [("_this", old_target["medium"])],
                )[0]
                box.wait_progress(progress, 60000)
            except Exception:
                pass

        target = cfg.bench / "target.vdi"
        if target.exists():
            target.unlink()

        medium = box._vals(
            "IVirtualBox_createMedium",
            [
                ("_this", box.handle),
                ("format", "VDI"),
                ("location", unc(target)),
                ("accessMode", "ReadWrite"),
                ("aDeviceTypeType", "HardDisk"),
            ],
        )[0]
        progress = box._vals(
            "IMedium_createBaseStorage",
            [
                ("_this", medium),
                ("logicalSize", str(cfg.target_size_gib * 1024**3)),
                ("variant", "Standard"),
            ],
        )[0]
        box.wait_progress(progress, 60000)
        if box._vals(
            "IProgress_getResultCode", [("_this", progress)]
        )[0] != "0":
            raise RuntimeError("target VDI creation failed")

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

            box._vals(
                "IMachine_setBootOrder",
                [
                    ("_this", machine),
                    ("position", "1"),
                    ("device", "DVD"),
                ],
            )
            box._vals(
                "IMachine_setBootOrder",
                [
                    ("_this", machine),
                    ("position", "2"),
                    ("device", "HardDisk"),
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

        serial = cfg.bench / "serial.log"
        if serial.exists():
            serial.unlink()

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
