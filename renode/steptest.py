#!/usr/bin/env python3
"""64-step patterns (Renode with run.resc). steptest.py program: on a fresh flash, build a 64-step pattern on
track 1 (step 1 = C4 on page 1, step 33 = E4 on page 2 via the right arrow), check paging and timing, save.
steptest.py verify: after a restart with the same flash, check the 64-step pattern was saved and plays."""
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

def lit(c): return c is not None and sum(c) > 150   # unlit steps are at most (24, 24, 24)

time.sleep(1.0)
press(97); time.sleep(0.5)
if sys.argv[1] == 'program':
    press(step_xy(1))                                   # step 1 = C4 (note pad 12 = 60, the default)
    press(92); time.sleep(0.3)                          # right arrow: page 2 (steps 33-64)
    arrows = (leds.get(91), leds.get(92))
    page2_step1_before = leds.get(step_xy(1))
    press(note_xy(16)); press(step_xy(1))               # step 33 = E4
    down(30); press(step_xy(32)); up(30)                # Fixed Length + pad 32 on page 2 = 64 steps
    time.sleep(0.3)
    print('arrows on page 2 (left, right):', arrows, ' step 33 before/after:', page2_step1_before, leds.get(step_xy(1)))
    ok &= arrows[1] == (252, 252, 252) and arrows[0] != (252, 252, 252) and lit(leds.get(step_xy(1))) and not lit(page2_step1_before)
    press(91); time.sleep(0.3)                          # back to page 1
    check('page 1 shows step 1 lit, step 2 unlit', (lit(leds.get(step_xy(1))), lit(leds.get(step_xy(2)))), (True, False))
r = play(6 * 64 + 6, spacing=0.02)
check('note-on pulses over 64 steps (step 1, step 33, step 1 again)', r.get(1), [1, 193, 385])
if sys.argv[1] == 'program':
    press(98); time.sleep(2.0)                          # save (version 5, 64 steps)
    print('Projects LED after save:', leds.get(98))
print('steptest', sys.argv[1], 'PASS' if ok else 'FAIL')
