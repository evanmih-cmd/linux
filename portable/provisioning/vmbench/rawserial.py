import re
import time
from pathlib import Path


def clean_text(data):
    text = data.decode("utf-8", "replace").replace("\r", "\n")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b[@-_]", "", text)
    return text.replace("\x0f", "").replace("\x0e", "")


class RawSerialMonitor:
    def __init__(self, path, run_dir, event):
        self.path = Path(path)
        self.run_dir = Path(run_dir)
        self.event = event

    def _bytes(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return b""

    def text(self):
        return clean_text(self._bytes())

    def mark(self):
        return len(self._bytes())

    def tail(self, size=40000):
        return self.text()[-size:]

    def wait_any(self, markers, timeout=60, new_since=None):
        if isinstance(markers, str):
            markers = [markers]
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._bytes()
            if new_since is not None:
                data = data[new_since:]
            text = clean_text(data)
            for marker in markers:
                if marker in text:
                    self.event("serial-match", marker=marker)
                    return marker
            time.sleep(0.25)
        raise TimeoutError(f"serial wait timed out: {markers!r}")

    def snapshot(self, name="serial.log"):
        dst = self.run_dir / name
        if dst.resolve() == self.path.resolve():
            return dst
        dst.write_bytes(self._bytes())
        return dst

    def close(self):
        self.snapshot()
