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
        matches = [
            m for m in machines
            if self._vals("IMachine_getName", [("_this", m)])[0]
            == self.cfg.vm_name
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one VM named {self.cfg.vm_name}, got {len(matches)}"
            )
        self.machine = matches[0]

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

    def unlock(self, session):
        self._vals("ISession_unlockMachine", [("_this", session)])

    def save_settings(self, machine):
        self._vals("IMachine_saveSettings", [("_this", machine)])

    def launch(self):
        if self.state() != "PoweredOff":
            raise RuntimeError(f"cannot launch from {self.state()}")
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
        self.wait_progress(progress, 30000)
        if self._vals(
            "IProgress_getResultCode", [("_this", progress)]
        )[0] != "0":
            raise RuntimeError("VirtualBox launch failed")
        return session

    def wait_progress(self, progress, timeout_ms):
        self._vals(
            "IProgress_waitForCompletion",
            [("_this", progress), ("timeout", str(timeout_ms))],
        )

    def poweroff(self):
        if self.state() != "Running":
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
