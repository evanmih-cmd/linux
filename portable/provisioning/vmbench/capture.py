import base64
import re
import time
from pathlib import Path

from config import Config
from vbox import VBOX


def screenshot(box, path):
    session = box.lock("Shared")
    try:
        console = box.session_console(session)
        display = box._vals(
            "IConsole_getDisplay", [("_this", console)]
        )[0]
        root = box._raw(
            "IDisplay_getScreenResolution",
            [("_this", display), ("screenId", "0")],
        )
        response = root.find(
            f".//{{{VBOX}}}IDisplay_getScreenResolutionResponse"
        )
        width = int(response.findtext("width"))
        height = int(response.findtext("height"))
        encoded = box._vals(
            "IDisplay_takeScreenShotToArray",
            [
                ("_this", display),
                ("screenId", "0"),
                ("width", width),
                ("height", height),
                ("bitmapFormat", "PNG"),
            ],
        )[0]
        Path(path).write_bytes(base64.b64decode(encoded))
        return width, height
    finally:
        box.unlock(session)


def serial_text(cfg=None):
    cfg = cfg or Config()
    path = cfg.bench / "serial.log"
    if not path.exists():
        return ""
    text = path.read_bytes().decode("utf-8", "replace")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b[@-_]", "", text)
    return text.replace("\x0f", "").replace("\x0e", "")


def wait_serial(needle, timeout=180, cfg=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if needle in serial_text(cfg):
            return True
        time.sleep(0.5)
    return False
