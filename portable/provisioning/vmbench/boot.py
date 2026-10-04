import time

from capture import wait_serial
from keyboard import Keyboard


CMDLINE_SUFFIX = " console=ttyS0,115200 console=tty0 textmode=1"


def boot_installer(box):
    launch_session = box.launch()
    keyboard = Keyboard(box)

    if not wait_serial("Please press", timeout=120, cfg=box.cfg):
        raise TimeoutError("GRUB serial marker not seen")

    keyboard.text("t")
    time.sleep(0.8)
    keyboard.edit()
    keyboard.down(4)
    keyboard.end()
    keyboard.text(CMDLINE_SUFFIX)
    keyboard.ctrl_x()

    return launch_session
