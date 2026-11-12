#!/usr/bin/env python3
"""Pattern Settings test (Renode with run.resc, fresh flash, external clock). Pattern Settings (69) opens a page for the
selected track's pattern: step pads set its length, the bottom row its step rate. Pattern 1 = 8 steps at 1/8, pattern 2
(new: inherits 8 x 1/8, then set to 16 x 1/16); chained, each keeps its own rate and pattern 2 starts on the bar line.
The rates survive saving and reopening the project."""
"""Per-track step rate test (Renode with run.resc, fresh flash.bin). Tracks 1 and 2 -> DIN 1 (channels 1, 2),
externally clocked (FA + F8s over USB). Note timing is measured in clock pulses on the DIN 1 byte stream."""
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

def pat_xy(p): return (8 - p // 8) * 10 + p % 8 + 1    # p: 0 = pattern / project 1 (top-left)
def white(xy): c = leds.get(xy); return c is not None and min(c) >= 240

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)
press(step_xy(1))                                       # track 1, pattern 1: step 1 on

press(69); time.sleep(0.3)                              # open Pattern Settings
c = leds.get(69)
check('Pattern Settings button orange when open', c is not None and c[0] > 200 and 60 < c[1] < 180 and c[2] < 40, True)
press(step_xy(8)); time.sleep(0.2)                      # length 8
check('step 8 white (last step), step 9 dim', (white(step_xy(8)), leds.get(step_xy(9))), (True, (8, 8, 8)))
press(note_xy(3)); time.sleep(0.2)                      # rate 1/8 (bottom row, 4th pad)
g = leds.get(note_xy(3))
check('1/8 rate pad bright green', g is not None and g[1] > 200, True)
press(69); time.sleep(0.3)                              # close
check('step 9 off past the end', leds.get(step_xy(9)), (0, 0, 0))

r = play(200)
check('pattern 1, 8 steps at 1/8: pulses', r.get(1), [1, 97, 193])

down(89); press(pat_xy(1)); up(89); time.sleep(0.3)     # pattern 2 (new: takes 8 steps at 1/8)
press(89); time.sleep(0.2)                              # close the latched view
press(69); time.sleep(0.3)
g = leds.get(note_xy(3))
check('new pattern 2 inherits 1/8 and length 8', (g is not None and g[1] > 200, white(step_xy(8))), (True, True))
press(note_xy(5)); press(step_xy(16)); time.sleep(0.2)  # 1/16, 16 steps
press(69); time.sleep(0.3)
press(step_xy(1))                                       # pattern 2: step 1 on
down(89); down(pat_xy(0)); press(pat_xy(1)); up(pat_xy(0)); up(89); time.sleep(0.3)   # chain 1-2
press(89); time.sleep(0.2)

r = play(400)
check('chain 1/8 x 8 then 1/16 x 16: pulses', r.get(1), [1, 97, 193, 289, 385])

press(98); time.sleep(1.5)                              # save project 1
down(98); press(pat_xy(1)); up(98); time.sleep(1.0)     # open project 2
down(98); press(pat_xy(0)); up(98); time.sleep(1.0)     # back to project 1
r = play(400)
check('after reopening the project: pulses', r.get(1), [1, 97, 193, 289, 385])

print('psettest', 'PASS' if ok else 'FAIL')
