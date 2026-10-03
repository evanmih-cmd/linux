import json
import time

from config import Config


KEY = {
    "a": 0x1e, "b": 0x30, "c": 0x2e, "d": 0x20,
    "e": 0x12, "f": 0x21, "g": 0x22, "h": 0x23,
    "i": 0x17, "j": 0x24, "k": 0x25, "l": 0x26,
    "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19,
    "q": 0x10, "r": 0x13, "s": 0x1f, "t": 0x14,
    "u": 0x16, "v": 0x2f, "w": 0x11, "x": 0x2d,
    "y": 0x15, "z": 0x2c,
    "0": 0x0b, "1": 0x02, "2": 0x03, "3": 0x04,
    "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08,
    "8": 0x09, "9": 0x0a,
    " ": 0x39, "/": 0x35, ".": 0x34, "-": 0x0c,
}
SHIFTED = {">": 0x34, "|": 0x2b, ":": 0x27}


class Keyboard:
    def __init__(self, box):
        self.box = box

    def _with_keyboard(self, action):
        session = self.box.lock("Shared")
        try:
            console = self.box.session_console(session)
            keyboard = self.box._vals(
                "IConsole_getKeyboard", [("_this", console)]
            )[0]
            action(keyboard)
        finally:
            self.box.unlock(session)

    def _scancode(self, keyboard, code):
        self.box._vals(
            "IKeyboard_putScancode",
            [("_this", keyboard), ("scancode", code)],
        )

    def _press(self, keyboard, code):
        self._scancode(keyboard, code)
        self._scancode(keyboard, code | 0x80)
        time.sleep(0.035)

    def text(self, text):
        def action(keyboard):
            for char in text:
                if char.isupper():
                    self._scancode(keyboard, 0x2a)
                    self._press(keyboard, KEY[char.lower()])
                    self._scancode(keyboard, 0xaa)
                elif char in SHIFTED:
                    self._scancode(keyboard, 0x2a)
                    self._press(keyboard, SHIFTED[char])
                    self._scancode(keyboard, 0xaa)
                else:
                    self._press(keyboard, KEY[char])
        self._with_keyboard(action)

    def enter(self):
        self._with_keyboard(lambda keyboard: self._press(keyboard, 0x1c))

    def f10(self):
        self._with_keyboard(lambda keyboard: self._press(keyboard, 0x44))

    def edit(self):
        self._with_keyboard(lambda keyboard: self._press(keyboard, 0x12))

    def down(self, count=1):
        def action(keyboard):
            for _ in range(count):
                for code in (0xe0, 0x50, 0xe0, 0xd0):
                    self._scancode(keyboard, code)
                    time.sleep(0.025)
        self._with_keyboard(action)

    def end(self):
        def action(keyboard):
            for code in (0xe0, 0x4f, 0xe0, 0xcf):
                self._scancode(keyboard, code)
                time.sleep(0.025)
        self._with_keyboard(action)

    def ctrl_x(self):
        def action(keyboard):
            self._scancode(keyboard, 0x1d)
            self._press(keyboard, 0x2d)
            self._scancode(keyboard, 0x9d)
        self._with_keyboard(action)

    def alt_fn(self, number):
        codes = {
            1: 0x3b, 2: 0x3c, 3: 0x3d, 4: 0x3e,
            5: 0x3f, 6: 0x40, 7: 0x41,
        }
        code = codes[number]

        def action(keyboard):
            self._scancode(keyboard, 0x38)
            self._press(keyboard, code)
            self._scancode(keyboard, 0xb8)

        self._with_keyboard(action)
        time.sleep(0.4)

    def fill(self, name, cfg=None):
        cfg = cfg or Config()
        value = json.loads(cfg.credentials.read_text())[name]
        self.text(value)
        self.f10()
