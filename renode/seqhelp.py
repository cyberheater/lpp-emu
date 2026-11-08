"""Shared test helpers for the sequencer tests."""
import socket
import time


def shift_gpio(high):
    """Shift (PA3) is a GPIO input on the MK3, not part of the M0 frame: drive it through the Renode monitor."""
    m = socket.create_connection(('127.0.0.1', 1234)); m.settimeout(0.3)
    try:
        m.recv(4096)
    except OSError:
        pass
    m.sendall(f'mach set 0\nsysbus.gpioPortA OnGPIO 3 {"true" if high else "false"}\n'.encode())
    time.sleep(0.3); m.close(); time.sleep(0.1)


def follow_external(press):
    """The sequencer runs on its internal clock by default; Shift + Play makes it follow an external MIDI clock."""
    shift_gpio(True)
    press(20)
    shift_gpio(False)
    # The monitor applies the Shift release asynchronously: give it time, or the test's next Play press would still
    # count as Shift + Play and switch the clock back instead of starting playback.
    time.sleep(0.8)
