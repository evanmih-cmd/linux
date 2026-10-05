import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from config import Config


SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
VBOX = "http://www.virtualbox.org/"


class VBox:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.handle = self._vals(
            "IWebsessionManager_logon",
            [("username", ""), ("password", "")]
        )[0]
        machines = self._vals(
            "IVirtualBox_getMachines",
            [("_this", self.handle)]
        )
        named = [
            (m, self._vals("IMachine_getName", [("_this", m)])[0])
            for m in machines
        ]
        matches = [m for m, name in named if name == self.cfg.vm_name]
        if len(matches) == 1:
            self.machine = matches[0]
        elif len(named) == 1:
            self.machine = named[0][0]
        else:
            names = ", ".join(name for _, name in named)
            raise RuntimeError(
                f"expected VM {self.cfg.vm_name!r} or one registered VM; "
                f"found {len(named)}: {names}"
            )
        self.actual_vm_name = self._vals(
            "IMachine_getName", [("_this", self.machine)]
        )[0]

    def _raw(self, op, pairs):
        env = ET.Element(f"{{{SOAP}}}Envelope")
        body = ET.SubElement(env, f"{{{SOAP}}}Body")
        node = ET.SubElement(body, f"{{{VBOX}}}{op}")
        for key, value in pairs:
            ET.SubElement(node, key).text = str(value)
        request = urllib.request.Request(
            self.cfg.ws_url,
            data=ET.tostring(env),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '""',
            },
        )
        try:
            data = urllib.request.urlopen(request, timeout=30).read()
        except urllib.error.HTTPError as exc:
            data = exc.read()
        root = ET.fromstring(data)
        fault = root.find(f".//{{{SOAP}}}Fault")
        if fault is not None:
            raise RuntimeError(
                f"{op}: {fault.findtext('faultstring') or 'fault'}"
            )
        return root

    def _vals(self, op, pairs):
        return [
            item.text or ""
            for item in self._raw(op, pairs).findall(".//returnval")
        ]

    def state(self):
        return self._vals(
            "IMachine_getState", [("_this", self.machine)]
        )[0]

    def session_state(self):
        return self._vals(
            "IMachine_getSessionState", [("_this", self.machine)]
        )[0]


    def log_folder(self):
        vals = self._vals(
            "IMachine_getLogFolder", [("_this", self.machine)]
        )
        return vals[0] if vals else ""

    def serial_config(self):
        serial = self._vals(
            "IMachine_getSerialPort",
            [("_this", self.machine), ("slot", "0")],
        )[0]
        def get(op):
            vals = self._vals(op, [("_this", serial)])
            return vals[0] if vals else None
        return {
            "enabled": get("ISerialPort_getEnabled"),
            "host_mode": get("ISerialPort_getHostMode"),
            "path": get("ISerialPort_getPath"),
            "server": get("ISerialPort_getServer"),
            "io_address": get("ISerialPort_getIOAddress"),
            "irq": get("ISerialPort_getIRQ"),
        }

    def set_serial_raw_file(self, path):
        if self.state() != "PoweredOff":
            raise RuntimeError(
                f"serial path can only be changed while PoweredOff, got {self.state()}"
            )
        session = self.lock("Write")
        try:
            machine = self.session_machine(session)
            serial = self._vals(
                "IMachine_getSerialPort",
                [("_this", machine), ("slot", "0")],
            )[0]
            for operation, key, value in (
                ("ISerialPort_setEnabled", "enabled", "true"),
                ("ISerialPort_setPath", "path", path),
                ("ISerialPort_setHostMode", "hostMode", "RawFile"),
            ):
                self._vals(
                    operation,
                    [("_this", serial), (key, value)],
                )
            self.save_settings(machine)
        finally:
            self.unlock(session)

    def cpu_count(self):
        return int(self._vals(
            "IMachine_getCPUCount", [("_this", self.machine)]
        )[0])

    def graphics_config(self):
        adapter = self._vals(
            "IMachine_getGraphicsAdapter", [("_this", self.machine)]
        )[0]
        return {
            "controller": self._vals(
                "IGraphicsAdapter_getGraphicsControllerType",
                [("_this", adapter)],
            )[0],
            "vram_mib": int(self._vals(
                "IGraphicsAdapter_getVRAMSize",
                [("_this", adapter)],
            )[0]),
            "accel3d": self._vals(
                "IGraphicsAdapter_isFeatureEnabled",
                [("_this", adapter), ("feature", "Acceleration3D")],
            )[0] == "true",
        }

    def attachments(self):
        out = []
        root = self._raw(
            "IMachine_getMediumAttachments", [("_this", self.machine)]
        )
        for item in root.findall(".//returnval"):
            medium = item.findtext("medium") or ""
            location = "EMPTY"
            if medium:
                location = self._vals(
                    "IMedium_getLocation", [("_this", medium)]
                )[0]
            out.append({
                "controller": item.findtext("controller"),
                "port": int(item.findtext("port")),
                "device": int(item.findtext("device")),
                "type": item.findtext("type"),
                "medium": medium,
                "location": location,
            })
        return out

    def close_hard_disks_at(self, location):
        closed = 0
        for medium in self._vals(
            "IVirtualBox_getHardDisks", [("_this", self.handle)]
        ):
            try:
                current = self._vals(
                    "IMedium_getLocation", [("_this", medium)]
                )[0]
            except Exception:
                continue
            if current != location:
                continue
            self._vals("IMedium_close", [("_this", medium)])
            closed += 1
        return closed

    def boot_nvram(self):
        nv = self._vals(
            "IMachine_getNonVolatileStore", [("_this", self.machine)]
        )[0]
        store = self._vals(
            "INvramStore_getUefiVariableStore", [("_this", nv)]
        )[0]
        root = self._raw(
            "IUefiVariableStore_queryVariables", [("_this", store)]
        )
        response = root.find(
            f".//{{{VBOX}}}IUefiVariableStore_queryVariablesResponse"
        )
        names = [x.text or "" for x in response.findall("names")]
        owners = [x.text or "" for x in response.findall("owners")]
        out = {}
        for name, owner in zip(names, owners):
            if not name.startswith("Boot"):
                continue
            item = self._raw(
                "IUefiVariableStore_queryVariableByName",
                [("_this", store), ("name", name)],
            ).find(
                f".//{{{VBOX}}}IUefiVariableStore_queryVariableByNameResponse"
            )
            out[name] = {
                "owner": owner,
                "data": item.findtext("data") or "",
            }
        return out

    def lock(self, lock_type):
        session = self._vals(
            "IWebsessionManager_getSessionObject",
            [("refIVirtualBox", self.handle)]
        )[0]
        self._vals(
            "IMachine_lockMachine",
            [
                ("_this", self.machine),
                ("session", session),
                ("lockType", lock_type),
            ],
        )
        return session

    def session_machine(self, session):
        return self._vals(
            "ISession_getMachine", [("_this", session)]
        )[0]

    def session_console(self, session):
        return self._vals(
            "ISession_getConsole", [("_this", session)]
        )[0]

    def guest_additions_run_level(self, session):
        console = self.session_console(session)
        guest = self._vals(
            "IConsole_getGuest", [("_this", console)]
        )[0]
        values = self._vals(
            "IGuest_getAdditionsRunLevel", [("_this", guest)]
        )
        return values[0] if values else "None"

    def unlock(self, session):
        self._vals("ISession_unlockMachine", [("_this", session)])

    def save_settings(self, machine):
        self._vals("IMachine_saveSettings", [("_this", machine)])

    def nvram_boot_variables(self):
        nvram = self._vals(
            "IMachine_getNonVolatileStore", [("_this", self.machine)]
        )[0]
        store = self._vals(
            "INvramStore_getUefiVariableStore", [("_this", nvram)]
        )[0]
        root = self._raw(
            "IUefiVariableStore_queryVariables", [("_this", store)]
        )
        response = root.find(
            f".//{{{VBOX}}}IUefiVariableStore_queryVariablesResponse"
        )
        names = [x.text or "" for x in response.findall("names")]
        owners = [x.text or "" for x in response.findall("owners")]
        out = {}
        for name, owner in zip(names, owners):
            if not name.startswith("Boot"):
                continue
            item = self._raw(
                "IUefiVariableStore_queryVariableByName",
                [("_this", store), ("name", name)],
            )
            resp = item.find(
                f".//{{{VBOX}}}IUefiVariableStore_queryVariableByNameResponse"
            )
            out[name] = {
                "owner": owner,
                "data": resp.findtext("data") or "",
            }
        return out


    def launch_begin(self):
        session = self._vals(
            "IWebsessionManager_getSessionObject",
            [("refIVirtualBox", self.handle)]
        )[0]
        progress = self._vals(
            "IMachine_launchVMProcess",
            [
                ("_this", self.machine),
                ("session", session),
                ("name", "headless"),
            ],
        )[0]
        return session, progress

    def launch_finish(self, progress, timeout_ms=30000):
        self.wait_progress(progress, timeout_ms)
        error = self.progress_error(progress)
        if error:
            raise RuntimeError(f"VirtualBox launch failed: {error}")

    def launch(self):
        session, progress = self.launch_begin()
        self.launch_finish(progress)
        return session

    def wait_progress(self, progress, timeout_ms):
        self._vals(
            "IProgress_waitForCompletion",
            [("_this", progress), ("timeout", str(timeout_ms))],
        )

    def progress_error(self, progress):
        code = self._vals(
            "IProgress_getResultCode", [("_this", progress)]
        )[0]
        if code == "0":
            return None
        info = self._vals(
            "IProgress_getErrorInfo", [("_this", progress)]
        )
        if not info or not info[0]:
            return f"resultCode={code}"
        try:
            text = self._vals(
                "IVirtualBoxErrorInfo_getText", [("_this", info[0])]
            )[0]
        except Exception:
            text = ""
        return f"resultCode={code} text={text}"

    def poweroff(self):
        if self.state() not in ("Running", "Paused"):
            return
        session = self.lock("Shared")
        try:
            console = self.session_console(session)
            progress = self._vals(
                "IConsole_powerDown", [("_this", console)]
            )[0]
            self.wait_progress(progress, 30000)
        finally:
            try:
                self.unlock(session)
            except Exception:
                pass

    def logoff(self):
        try:
            self._vals(
                "IWebsessionManager_logoff",
                [("refIVirtualBox", self.handle)]
            )
        except Exception:
            pass
