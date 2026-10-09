import base64
import hashlib
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from config import Config


SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
VBOX = "http://www.virtualbox.org/"


class VBoxError(RuntimeError):
    pass


class VBox:
    """Small raw-SOAP VirtualBox client.

    The Windows bench deliberately uses vboxwebsrv only. The host CLI is not a
    harness dependency.
    """

    def __init__(self, cfg=None, require_machine=False):
        self.cfg = cfg or Config()
        self.handle = self._vals(
            "IWebsessionManager_logon",
            [("username", ""), ("password", "")],
        )[0]
        self.machine = self.find_machine(self.cfg.vm_name)
        if require_machine and not self.machine:
            raise VBoxError(f"VM {self.cfg.vm_name!r} is not registered")

    def _raw(self, op, pairs, timeout=30):
        env = ET.Element(f"{{{SOAP}}}Envelope")
        body = ET.SubElement(env, f"{{{SOAP}}}Body")
        node = ET.SubElement(body, f"{{{VBOX}}}{op}")
        for key, value in pairs:
            child = ET.SubElement(node, key)
            child.text = "" if value is None else str(value)

        request = urllib.request.Request(
            self.cfg.ws_url,
            data=ET.tostring(env),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '""',
            },
        )
        try:
            data = urllib.request.urlopen(request, timeout=timeout).read()
        except urllib.error.HTTPError as exc:
            data = exc.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise VBoxError(
                f"{op}: VirtualBox WebService unavailable at "
                f"{self.cfg.ws_url}: {exc}"
            ) from exc

        root = ET.fromstring(data)
        fault = root.find(f".//{{{SOAP}}}Fault")
        if fault is not None:
            message = fault.findtext("faultstring") or "SOAP fault"
            detail = " ".join(
                text.strip()
                for text in fault.itertext()
                if text and text.strip() and text.strip() != message
            )
            raise VBoxError(f"{op}: {message}" + (f" ({detail})" if detail else ""))
        return root

    def _vals(self, op, pairs, timeout=30):
        return [
            item.text or ""
            for item in self._raw(op, pairs, timeout=timeout).findall(".//returnval")
        ]

    def call(self, op, pairs=(), timeout=30):
        self._raw(op, list(pairs), timeout=timeout)

    def version(self):
        return self._vals("IVirtualBox_getVersion", [("_this", self.handle)])[0]

    def machines(self):
        result = []
        for machine in self._vals(
            "IVirtualBox_getMachines", [("_this", self.handle)]
        ):
            result.append(
                {
                    "handle": machine,
                    "name": self._vals(
                        "IMachine_getName", [("_this", machine)]
                    )[0],
                    "state": self._vals(
                        "IMachine_getState", [("_this", machine)]
                    )[0],
                }
            )
        return result

    def find_machine(self, name):
        matches = [x["handle"] for x in self.machines() if x["name"] == name]
        if len(matches) > 1:
            raise VBoxError(f"multiple VMs named {name!r}")
        return matches[0] if matches else None

    def refresh_machine(self):
        self.machine = self.find_machine(self.cfg.vm_name)
        return self.machine

    def require_machine(self):
        if not self.machine:
            self.refresh_machine()
        if not self.machine:
            raise VBoxError(f"VM {self.cfg.vm_name!r} is not registered")
        return self.machine

    def state(self):
        machine = self.require_machine()
        return self._vals("IMachine_getState", [("_this", machine)])[0]

    def description(self):
        machine = self.require_machine()
        values = self._vals("IMachine_getDescription", [("_this", machine)])
        return values[0] if values else ""

    def session_state(self):
        machine = self.require_machine()
        return self._vals("IMachine_getSessionState", [("_this", machine)])[0]

    def lock(self, lock_type, machine=None):
        machine = machine or self.require_machine()
        session = self._vals(
            "IWebsessionManager_getSessionObject",
            [("refIVirtualBox", self.handle)],
        )[0]
        self._vals(
            "IMachine_lockMachine",
            [
                ("_this", machine),
                ("session", session),
                ("lockType", lock_type),
            ],
        )
        return session

    def session_machine(self, session):
        return self._vals("ISession_getMachine", [("_this", session)])[0]

    def session_console(self, session):
        return self._vals("ISession_getConsole", [("_this", session)])[0]

    def unlock(self, session):
        self._vals("ISession_unlockMachine", [("_this", session)])

    def save_settings(self, machine):
        self._vals("IMachine_saveSettings", [("_this", machine)])

    def wait_progress(self, progress, timeout_ms):
        self._vals(
            "IProgress_waitForCompletion",
            [("_this", progress), ("timeout", str(timeout_ms))],
            timeout=max(30, int(timeout_ms / 1000) + 5),
        )

    def progress_error(self, progress):
        code = self._vals("IProgress_getResultCode", [("_this", progress)])[0]
        if code == "0":
            return None
        info = self._vals("IProgress_getErrorInfo", [("_this", progress)])
        if not info or not info[0]:
            return f"resultCode={code}"
        try:
            text = self._vals(
                "IVirtualBoxErrorInfo_getText", [("_this", info[0])]
            )[0]
        except Exception:
            text = ""
        return f"resultCode={code} text={text}"

    def wait_progress_ok(self, progress, timeout_ms, label):
        self.wait_progress(progress, timeout_ms)
        error = self.progress_error(progress)
        if error:
            raise VBoxError(f"{label} failed: {error}")

    def launch(self):
        machine = self.require_machine()
        session = self._vals(
            "IWebsessionManager_getSessionObject",
            [("refIVirtualBox", self.handle)],
        )[0]
        progress = self._vals(
            "IMachine_launchVMProcess",
            [
                ("_this", machine),
                ("session", session),
                ("name", "headless"),
            ],
        )[0]
        self.wait_progress_ok(progress, 60000, "VM launch")
        return session

    def framebuffer_evidence(self):
        if self.state() != "Running":
            return {
                "vm_state": self.state(),
                "resolution": [0, 0],
                "sha256": None,
                "nonblack_pixels": 0,
                "bright_pixels": 0,
                "is_black": True,
            }

        session = self.lock("Shared")
        try:
            console = self.session_console(session)
            display = self._vals(
                "IConsole_getDisplay", [("_this", console)]
            )[0]
            resolution = self._raw(
                "IDisplay_getScreenResolution",
                [("_this", display), ("screenId", "0")],
            )
            width = int(resolution.findtext(".//width") or "0")
            height = int(resolution.findtext(".//height") or "0")
            if width <= 0 or height <= 0:
                return {
                    "vm_state": "Running",
                    "resolution": [width, height],
                    "sha256": None,
                    "nonblack_pixels": 0,
                    "bright_pixels": 0,
                    "is_black": True,
                }

            shot = self._raw(
                "IDisplay_takeScreenShotToArray",
                [
                    ("_this", display),
                    ("screenId", "0"),
                    ("width", str(width)),
                    ("height", str(height)),
                    ("bitmapFormat", "BGR0"),
                ],
            )
            values = [
                item.text or "" for item in shot.findall(".//returnval")
            ]
            if not values:
                raise VBoxError("framebuffer screenshot returned no data")
            pixels = base64.b64decode(values[0])
            nonblack = 0
            bright = 0
            for p in range(0, len(pixels), 4):
                b, g, r = pixels[p], pixels[p + 1], pixels[p + 2]
                if max(r, g, b) >= 24:
                    nonblack += 1
                if r >= 120 and g >= 120 and b >= 120:
                    bright += 1
            total = max(1, width * height)
            return {
                "vm_state": "Running",
                "resolution": [width, height],
                "sha256": hashlib.sha256(pixels).hexdigest(),
                "nonblack_pixels": nonblack,
                "bright_pixels": bright,
                "nonblack_ratio": round(nonblack / total, 6),
                "is_black": nonblack <= max(64, total // 2000),
            }
        finally:
            self.unlock(session)

    def accept_optical_boot_prompt(
        self,
        *,
        timeout_seconds=60,
        poll_interval_seconds=0.12,
    ):
        """Wait for the one-line DVD boot prompt, then press Enter once.

        Detection uses framebuffer geometry rather than an exact screenshot
        hash, so harmless firmware/font/rendering differences do not make the
        harness brittle.  A key is sent only when the upper framebuffer looks
        like one line of bright firmware text on a dark background.  This is
        boot orchestration only, never guest command transport.
        """
        if self.state() != "Running":
            raise VBoxError(
                f"boot prompt acceptance requires Running VM, got {self.state()}"
            )

        started = time.monotonic()
        deadline = started + timeout_seconds
        last_evidence = None

        while time.monotonic() < deadline:
            session = self.lock("Shared")
            try:
                console = self.session_console(session)
                display = self._vals(
                    "IConsole_getDisplay", [("_this", console)]
                )[0]
                resolution = self._raw(
                    "IDisplay_getScreenResolution",
                    [("_this", display), ("screenId", "0")],
                )
                width = int(resolution.findtext(".//width") or "0")
                height = int(resolution.findtext(".//height") or "0")
                if width <= 0 or height <= 0:
                    continue

                shot = self._raw(
                    "IDisplay_takeScreenShotToArray",
                    [
                        ("_this", display),
                        ("screenId", "0"),
                        ("width", str(width)),
                        ("height", str(height)),
                        ("bitmapFormat", "BGR0"),
                    ],
                )
                values = [
                    item.text or ""
                    for item in shot.findall(".//returnval")
                ]
                if not values:
                    continue

                pixels = base64.b64decode(values[0])
                scan_height = min(height, 120)
                row_counts = []
                bright_total = 0
                max_x = -1
                for y in range(scan_height):
                    row = 0
                    base = y * width * 4
                    for x in range(width):
                        p = base + x * 4
                        b, g, r = pixels[p], pixels[p + 1], pixels[p + 2]
                        if r >= 120 and g >= 120 and b >= 120:
                            row += 1
                            max_x = max(max_x, x)
                    row_counts.append(row)
                    bright_total += row

                active_rows = [
                    y for y, count in enumerate(row_counts) if count >= 4
                ]
                runs = []
                for y in active_rows:
                    if not runs or y > runs[-1][-1] + 1:
                        runs.append([y])
                    else:
                        runs[-1].append(y)

                main_runs = [run for run in runs if len(run) >= 6]
                fragments = [run for run in runs if 2 <= len(run) < 6]
                fragment_ok = False
                if len(main_runs) == 1:
                    main_end = main_runs[0][-1]
                    fragment_ok = all(
                        run[0] <= main_end + 6 for run in fragments
                    )
                one_line = (
                    len(main_runs) == 1
                    and 6 <= len(main_runs[0]) <= 24
                    and main_runs[0][0] < 80
                    and fragment_ok
                    and 100 <= bright_total <= 12000
                    and 120 <= max_x <= min(width - 1, 900)
                )
                last_evidence = {
                    "resolution": [width, height],
                    "bright_total": bright_total,
                    "main_row_runs": [
                        [run[0], run[-1]] for run in main_runs
                    ],
                    "fragment_row_runs": [
                        [run[0], run[-1]] for run in fragments
                    ],
                    "max_x": max_x,
                }

                if one_line:
                    keyboard = self._vals(
                        "IConsole_getKeyboard", [("_this", console)]
                    )[0]
                    accepted = self._vals(
                        "IKeyboard_putScancodes",
                        [
                            ("_this", keyboard),
                            ("scancodes", str(0x1C)),
                            ("scancodes", str(0x9C)),
                        ],
                    )
                    count = int(accepted[0]) if accepted else 0
                    if count != 2:
                        raise VBoxError(
                            "VirtualBox did not accept both Enter scan codes; "
                            f"accepted={count}"
                        )
                    return {
                        "status": "PASS",
                        "key": "Enter",
                        "scan_code_set": "Set-1 via USBKeyboard",
                        "accepted_scancodes": count,
                        "elapsed_seconds": round(
                            time.monotonic() - started, 3
                        ),
                        "detector": last_evidence,
                        "scope": "one-line optical-boot prompt only",
                    }
            finally:
                self.unlock(session)
            time.sleep(poll_interval_seconds)

        raise VBoxError(
            "optical boot prompt was not observed within "
            f"{timeout_seconds}s; last_evidence={last_evidence!r}"
        )

    def poweroff(self):
        if self.state() not in ("Running", "Paused", "Stuck"):
            return
        session = self.lock("Shared")
        try:
            console = self.session_console(session)
            progress = self._vals(
                "IConsole_powerDown", [("_this", console)]
            )[0]
            self.wait_progress_ok(progress, 60000, "VM poweroff")
        finally:
            try:
                self.unlock(session)
            except Exception:
                pass

    def discard_saved_state(self):
        if self.state() not in ("Saved", "AbortedSaved"):
            return
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            self._vals(
                "IMachine_discardSavedState",
                [("_this", machine), ("fRemoveFile", "true")],
            )
        finally:
            self.unlock(session)

    def create_machine(self, name, os_type="Windows11_64"):
        if self.find_machine(name):
            raise VBoxError(f"VM {name!r} already exists")
        vals = self._vals(
            "IVirtualBox_createMachine",
            [
                ("_this", self.handle),
                ("settingsFile", ""),
                ("name", name),
                ("platform", "x86"),
                ("groups", "/"),
                ("osTypeId", os_type),
                ("flags", ""),
                ("cipher", ""),
                ("passwordId", ""),
                ("password", ""),
            ],
        )
        if not vals:
            raise VBoxError("createMachine returned no machine handle")
        machine = vals[0]
        self._vals(
            "IVirtualBox_registerMachine",
            [("_this", self.handle), ("machine", machine)],
        )
        self.machine = machine
        return machine

    def unregister_and_delete(self):
        machine = self.require_machine()
        state = self.state()
        if state in ("Running", "Paused", "Stuck"):
            self.poweroff()
            state = self.state()
        if state in ("Saved", "AbortedSaved"):
            self.discard_saved_state()
        if self.state() != "PoweredOff":
            raise VBoxError(f"refusing to delete VM in state {self.state()}")

        # Preserve removable media such as official installation ISOs.
        # VirtualBox documents DetachAllReturnHardDisksOnly as the normal
        # delete-VM path; CleanupMode=Full also returns DVDs/floppies and
        # passing those to deleteConfig can delete their backing files.
        media = self._vals(
            "IMachine_unregister",
            [
                ("_this", machine),
                ("cleanupMode", "DetachAllReturnHardDisksOnly"),
            ],
        )
        pairs = [("_this", machine)] + [("media", item) for item in media]
        progress = self._vals("IMachine_deleteConfig", pairs)[0]
        self.wait_progress_ok(progress, 180000, "VM delete")
        self.machine = None

    def create_medium(
        self,
        location,
        size_bytes,
        *,
        format="VDI",
        variant="Standard",
    ):
        medium = self._vals(
            "IVirtualBox_createMedium",
            [
                ("_this", self.handle),
                ("format", format),
                ("location", location),
                ("accessMode", "ReadWrite"),
                ("aDeviceTypeType", "HardDisk"),
            ],
        )[0]
        progress = self._vals(
            "IMedium_createBaseStorage",
            [
                ("_this", medium),
                ("logicalSize", str(size_bytes)),
                ("variant", variant),
            ],
        )[0]
        self.wait_progress_ok(
            progress,
            180000,
            f"{format} creation",
        )
        return medium

    def configure_windows_hardware(self, disk_medium, *, disk_port=0):
        session = self.lock("Write")
        nested_hwvirt = None
        try:
            machine = self.session_machine(session)
            self._vals(
                "IMachine_setDescription",
                [
                    ("_this", machine),
                    ("description", "Managed by windows/vm/harness (#6)"),
                ],
            )
            self._vals(
                "IMachine_setMemorySize",
                [("_this", machine), ("memorySize", str(self.cfg.vm_memory_mib))],
            )
            self._vals(
                "IMachine_setCPUCount",
                [("_this", machine), ("CPUCount", str(self.cfg.vm_vcpus))],
            )

            firmware = self._vals(
                "IMachine_getFirmwareSettings", [("_this", machine)]
            )[0]
            self._vals(
                "IFirmwareSettings_setFirmwareType",
                [("_this", firmware), ("firmwareType", "EFI64")],
            )

            self._vals(
                "IMachine_setKeyboardHIDType",
                [
                    ("_this", machine),
                    ("keyboardHIDType", self.cfg.vm_keyboard_hid),
                ],
            )

            graphics = self._vals(
                "IMachine_getGraphicsAdapter", [("_this", machine)]
            )[0]
            self._vals(
                "IGraphicsAdapter_setGraphicsControllerType",
                [
                    ("_this", graphics),
                    ("graphicsControllerType", self.cfg.vm_graphics_controller),
                ],
            )
            self._vals(
                "IGraphicsAdapter_setVRAMSize",
                [
                    ("_this", graphics),
                    ("VRAMSize", str(self.cfg.vm_vram_mib)),
                ],
            )
            self._vals(
                "IGraphicsAdapter_setFeature",
                [
                    ("_this", graphics),
                    ("feature", "Acceleration3D"),
                    ("enabled", str(self.cfg.vm_accel3d).lower()),
                ],
            )

            tpm = self._vals(
                "IMachine_getTrustedPlatformModule", [("_this", machine)]
            )[0]
            self._vals(
                "ITrustedPlatformModule_setType",
                [("_this", tpm), ("type", "v2_0")],
            )

            try:
                platform = self._vals(
                    "IMachine_getPlatform", [("_this", machine)]
                )[0]
                x86 = self._vals(
                    "IPlatform_getX86", [("_this", platform)]
                )[0]
                self._vals(
                    "IPlatformX86_setCPUProperty",
                    [
                        ("_this", x86),
                        ("property", "HWVirt"),
                        ("value", str(self.cfg.vm_nested_hwvirt).lower()),
                    ],
                )
                nested_hwvirt = self.cfg.vm_nested_hwvirt
            except Exception:
                # Nested virtualization is useful for exercising VBS but is not
                # a prerequisite for the installation bench itself.
                nested_hwvirt = None

            controller = self._vals(
                "IMachine_addStorageController",
                [("_this", machine), ("name", "SATA"), ("connectionType", "SATA")],
            )[0]
            self._vals(
                "IStorageController_setControllerType",
                [("_this", controller), ("controllerType", "IntelAhci")],
            )
            self._vals(
                "IStorageController_setPortCount",
                [("_this", controller), ("portCount", "8")],
            )
            self._vals(
                "IMachine_attachDevice",
                [
                    ("_this", machine),
                    ("name", "SATA"),
                    ("controllerPort", str(disk_port)),
                    ("device", "0"),
                    ("type", "HardDisk"),
                    ("medium", disk_medium),
                ],
            )

            adapter = self._vals(
                "IMachine_getNetworkAdapter",
                [("_this", machine), ("slot", "0")],
            )[0]
            # Setup/OOBE must be network-independent.  Keep the
            # adapter configured for NAT but disabled until the clean
            # installed checkpoint has been reached.
            self._vals(
                "INetworkAdapter_setEnabled",
                [("_this", adapter), ("enabled", "false")],
            )
            self._vals(
                "INetworkAdapter_setAttachmentType",
                [("_this", adapter), ("attachmentType", "NAT")],
            )
            self.save_settings(machine)
        finally:
            self.unlock(session)

        # Secure Boot variable-store initialization is separate because the
        # NVRAM interfaces are backed by the registered machine.
        self.configure_secure_boot()
        return {"nested_hwvirt": nested_hwvirt}

    def attach_hard_disk(self, medium, port):
        if self.state() != "PoweredOff":
            raise VBoxError("disk attachment requires PoweredOff VM")
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            self._vals(
                "IMachine_attachDevice",
                [("_this", machine), ("name", "SATA"),
                 ("controllerPort", str(port)), ("device", "0"),
                 ("type", "HardDisk"), ("medium", medium)],
            )
            self.save_settings(machine)
        finally:
            self.unlock(session)

    def set_network_enabled(self, enabled):
        if self.state() != "PoweredOff":
            raise VBoxError(
                "network adapter enable/disable requires PoweredOff VM"
            )
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            adapter = self._vals(
                "IMachine_getNetworkAdapter",
                [("_this", machine), ("slot", "0")],
            )[0]
            self._vals(
                "INetworkAdapter_setAttachmentType",
                [("_this", adapter), ("attachmentType", "NAT")],
            )
            self._vals(
                "INetworkAdapter_setEnabled",
                [
                    ("_this", adapter),
                    ("enabled", str(bool(enabled)).lower()),
                ],
            )
            self.save_settings(machine)
        finally:
            self.unlock(session)
        return {"enabled": bool(enabled), "attachment_type": "NAT"}

    def network_config(self):
        machine = self.require_machine()
        adapter = self._vals(
            "IMachine_getNetworkAdapter",
            [("_this", machine), ("slot", "0")],
        )[0]
        return {
            "enabled": self._vals(
                "INetworkAdapter_getEnabled", [("_this", adapter)]
            )[0]
            == "true",
            "attachment_type": self._vals(
                "INetworkAdapter_getAttachmentType", [("_this", adapter)]
            )[0],
        }

    def configure_secure_boot(self):
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            nvram = self._vals(
                "IMachine_getNonVolatileStore", [("_this", machine)]
            )[0]
            self._vals(
                "INvramStore_initUefiVariableStore",
                [("_this", nvram), ("size", "0")],
            )
            store = self._vals(
                "INvramStore_getUefiVariableStore", [("_this", nvram)]
            )[0]
            self._vals(
                "IUefiVariableStore_enrollDefaultMsSignatures",
                [("_this", store)],
            )
            self._vals(
                "IUefiVariableStore_enrollOraclePlatformKey",
                [("_this", store)],
            )
            self._vals(
                "IUefiVariableStore_setSecureBootEnabled",
                [("_this", store), ("secureBootEnabled", "true")],
            )
            self.save_settings(machine)
        finally:
            self.unlock(session)

    def keyboard_hid_type(self):
        machine = self.require_machine()
        return self._vals(
            "IMachine_getKeyboardHIDType", [("_this", machine)]
        )[0]

    def graphics_config(self):
        machine = self.require_machine()
        adapter = self._vals(
            "IMachine_getGraphicsAdapter", [("_this", machine)]
        )[0]
        return {
            "controller": self._vals(
                "IGraphicsAdapter_getGraphicsControllerType",
                [("_this", adapter)],
            )[0],
            "vram_mib": int(
                self._vals(
                    "IGraphicsAdapter_getVRAMSize", [("_this", adapter)]
                )[0]
            ),
            "accel3d": self._vals(
                "IGraphicsAdapter_isFeatureEnabled",
                [("_this", adapter), ("feature", "Acceleration3D")],
            )[0]
            == "true",
        }

    def firmware_type(self):
        machine = self.require_machine()
        fw = self._vals(
            "IMachine_getFirmwareSettings", [("_this", machine)]
        )[0]
        return self._vals(
            "IFirmwareSettings_getFirmwareType", [("_this", fw)]
        )[0]

    def tpm_type(self):
        machine = self.require_machine()
        tpm = self._vals(
            "IMachine_getTrustedPlatformModule", [("_this", machine)]
        )[0]
        return self._vals("ITrustedPlatformModule_getType", [("_this", tpm)])[0]

    def secure_boot_enabled(self):
        machine = self.require_machine()
        nvram = self._vals(
            "IMachine_getNonVolatileStore", [("_this", machine)]
        )[0]
        store = self._vals(
            "INvramStore_getUefiVariableStore", [("_this", nvram)]
        )[0]
        return (
            self._vals(
                "IUefiVariableStore_getSecureBootEnabled", [("_this", store)]
            )[0]
            == "true"
        )

    def guest_additions_run_level(self):
        session = self.lock("Shared")
        try:
            console = self.session_console(session)
            guest = self._vals("IConsole_getGuest", [("_this", console)])[0]
            values = self._vals(
                "IGuest_getAdditionsRunLevel", [("_this", guest)]
            )
            return values[0] if values else "None"
        finally:
            self.unlock(session)

    def take_snapshot(self, name, description=""):
        if self.state() != "PoweredOff":
            raise VBoxError(
                "harness checkpoint snapshots require PoweredOff VM"
            )

        # The 7.2.20 WebService exports IMachine::takeSnapshot but, for an
        # offline mutable session machine, pause=false incorrectly selects the
        # live-snapshot path and fails with VBOX_E_INVALID_VM_STATE.  The SDK
        # specifies that pause is irrelevant for PoweredOff snapshots.  Using
        # true therefore preserves offline semantics and works with this SOAP
        # implementation.
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            root = self._raw(
                "IMachine_takeSnapshot",
                [
                    ("_this", machine),
                    ("name", name),
                    ("description", description),
                    ("pause", "true"),
                ],
            )
            vals = [x.text or "" for x in root.findall(".//returnval")]
            if not vals:
                raise VBoxError("takeSnapshot returned no progress")
            self.wait_progress_ok(vals[0], 180000, f"snapshot {name}")
        finally:
            self.unlock(session)

        snapshot = self._vals(
            "IMachine_findSnapshot",
            [("_this", self.machine), ("nameOrId", name)],
        )[0]
        return self._vals(
            "ISnapshot_getId", [("_this", snapshot)]
        )[0]

    def restore_snapshot(self, name):
        machine = self.require_machine()
        if self.state() != "PoweredOff":
            raise VBoxError("snapshot restore requires PoweredOff VM")
        snapshot = self._vals(
            "IMachine_findSnapshot",
            [("_this", machine), ("nameOrId", name)],
        )[0]
        session = self.lock("Write")
        try:
            mutable = self.session_machine(session)
            progress = self._vals(
                "IMachine_restoreSnapshot",
                [("_this", mutable), ("snapshot", snapshot)],
            )[0]
            self.wait_progress_ok(progress, 180000, f"restore snapshot {name}")
        finally:
            self.unlock(session)

    def logoff(self):
        try:
            self._vals(
                "IWebsessionManager_logoff",
                [("refIVirtualBox", self.handle)],
            )
        except Exception:
            pass
