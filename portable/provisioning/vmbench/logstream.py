import time

from keyboard import Keyboard


Y2LOG_COMMAND = "tail -F /var/log/YaST2/y2log >/dev/ttyS0"


def enable_y2log(box):
    keyboard = Keyboard(box)
    keyboard.alt_fn(2)
    time.sleep(0.5)
    keyboard.text(Y2LOG_COMMAND)
    keyboard.enter()
    time.sleep(0.8)
    keyboard.alt_fn(7)
