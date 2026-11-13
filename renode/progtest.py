#!/usr/bin/env python3
"""Programs page test (Renode with run.resc, fresh flash). Programs (19) opens the page: track 1 gets bank 5 +
program 8, the project slot (Device, 7) channel 16 + bank 1 + program 35, track 2 program 8 (no bank). Choosing sends
at once; saving, opening project 2 and coming back sends the project slot first, then the tracks; tapping the current
project again re-sends."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL, HW_LED_TO_LOGICAL  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
leds, din_log = {}, []
lock = threading.Lock()

def reader(sock, fn):
    buf = b''
    while True:
        d = sock.recv(65536)
        if not d:
            return
        buf += d
        *lines, buf = buf.split(b'\n')
        with lock:
            for ln in lines:
                fn(ln.decode())

def on_panel(ln):
    f = ln.split()
    if len(f) == 5 and f[0] == 'l' and HW_LED_TO_LOGICAL.get(int(f[1])) is not None:
        leds[HW_LED_TO_LOGICAL[int(f[1])]] = tuple(map(int, f[2:]))

def on_din(ln):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o' and f[1] == '1':
        din_log.extend(expand(1, int(f[2], 16)))

for s, fn in ((panel, on_panel), (din, on_din), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.1)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.1)
def press(lg): down(lg); up(lg)

def gpio(pin, high):
    """Setup (PA2) and Shift (PA3) are GPIO inputs on the MK3, not part of the M0 frame."""
    m = socket.create_connection(('127.0.0.1', 1234)); m.settimeout(0.3)
    try:
        m.recv(4096)
    except OSError:
        pass
    m.sendall(f'mach set 0\nsysbus.gpioPortA OnGPIO {pin} {"true" if high else "false"}\n'.encode())
    time.sleep(0.3); m.close(); time.sleep(0.1)

def shift(on): gpio(3, on)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

def play(pulses, spacing=0.03):
    """Returns {channel: [pulse_number, ...]} for every note-on on DIN 1."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(spacing)
    for _ in range(pulses):
        usb.sendall(b'm 1ff80000\n'); time.sleep(spacing)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    out, n, i = {}, 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x90 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i + 2] > 0:
                out.setdefault((b[i] & 15) + 1, []).append(n)
            i += 3
        else:
            i += 1
    return out


ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f'{label}: {got} (expect {want})', 'ok' if good else 'FAIL')

def pat_xy(p): return (8 - p // 8) * 10 + p % 8 + 1    # p: 0 = project 1 (top-left)
def prog_xy(n): return (1 + n // 8) * 10 + n % 8 + 1   # n: 0-31 within the group shown (row 1 = 0-7)
def sent(action, wait=0.4):
    with lock:
        din_log.clear()
    action(); time.sleep(wait)
    with lock:
        return [b for b in din_log if b < 0xF8]

time.sleep(1.0)
press(97); time.sleep(0.5)
press(step_xy(1))

press(19); time.sleep(0.3)
c = leds.get(19)
check('Programs button yellow when open', c is not None and c[0] > 200 and c[1] > 150 and c[2] < 40, True)
check('bank 5 alone sends nothing', sent(lambda: press(66)), [])
check('track 1 program 8 (pad 8) sends bank 5 + program', sent(lambda: press(prog_xy(7))), [0xB0, 32, 5, 0xC0, 7])
check('program pad white', min(leds.get(prog_xy(7), (0, 0, 0))) >= 240, True)

press(7); time.sleep(0.2)                                # project slot
check('project slot: no program shown', any(min(leds.get(prog_xy(n), (0, 0, 0))) >= 240 for n in range(32)), False)
press(78); press(62); press(80); time.sleep(0.2)          # channel 16, bank 1, ▲ = programs 33-64
check('project slot program 35 sends on channel 16', sent(lambda: press(prog_xy(2))), [0xBF, 32, 1, 0xCF, 34])

press(102); time.sleep(0.2)                              # track 2 (channel 2), group still 33-64
check('▼ lit on 33-64', leds.get(70, (0, 0, 0))[0] > 200, True)
press(70); time.sleep(0.2)                               # ▼ = programs 1-32
check('▼ dark on 1-32', leds.get(70, (0, 0, 0))[0] < 40, True)
check('track 2 program 8, no bank', sent(lambda: press(prog_xy(7))), [0xC1, 7])
press(19); time.sleep(0.3)

press(98); time.sleep(1.5)                               # save project 1
expect = [0xBF, 32, 1, 0xCF, 34, 0xB0, 32, 5, 0xC0, 7, 0xC1, 7]
check('open empty project 2 sends nothing', sent(lambda: (down(98), press(pat_xy(1)), up(98)), 1.0), [])
check('back to project 1 sends all', sent(lambda: (down(98), press(pat_xy(0)), up(98)), 1.0), expect)
check('tap current project re-sends', sent(lambda: (down(98), press(pat_xy(0)), up(98)), 1.0), expect)

press(19); time.sleep(0.3)
check('reloaded: track 2 program 8 white', min(leds.get(prog_xy(7), (0, 0, 0))) >= 240, True)
check('tapping it again = none, sends nothing', sent(lambda: press(prog_xy(7))), [])

print('progtest', 'PASS' if ok else 'FAIL')
