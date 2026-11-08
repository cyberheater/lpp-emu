#!/usr/bin/env python3
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

time.sleep(1.0)
press(97); time.sleep(0.5)
for s in range(1, 5):                                   # track 1: steps 1-4, note 60
    press(step_xy(s))
press(102); press(note_xy(16))                          # track 2: steps 1-4, note 64
for s in range(1, 5):
    press(step_xy(s))
press(101)

r = play(48)
check('both at 1/16: track 1 pulses', r.get(1), [1, 7, 13, 19])
check('both at 1/16: track 2 pulses', r.get(2), [1, 7, 13, 19])

press(98); time.sleep(1.5)                              # save: Projects green
projects_before = leds.get(98)
down(101); press(step_xy(21)); time.sleep(0.3)          # track 1 -> 1/8
rate_leds = [leds.get(step_xy(17 + k)) for k in range(8)]
up(101); time.sleep(0.3)
print('rate pads 17-24 with track 1 held (1/8 chosen):', rate_leds)
ok &= rate_leds[4] == max(rate_leds, key=lambda c: sum(c or (0, 0, 0))) and rate_leds[1][2] > rate_leds[1][1]
projects_after = leds.get(98)
print('Projects LED after save', projects_before, '-> after rate change', projects_after, '(green -> amber: the rate is saved with the project)')
ok &= projects_before[1] > projects_before[0] and projects_after[0] > projects_after[1]
r = play(48)
check('track 1 at 1/8: pulses', r.get(1), [1, 13, 25, 37])
check('track 2 still 1/16: pulses', r.get(2), [1, 7, 13, 19])

down(101); press(step_xy(18)); up(101)                  # track 1 -> 1/16 triplet
down(102); press(step_xy(23)); up(102)                  # track 2 -> 1/4
r = play(100)
check('track 1 at 1/16T: pulses', r.get(1)[:5], [1, 5, 9, 13, 65])   # 4 notes in 16 steps x 4 pulses
check('track 2 at 1/4: pulses', r.get(2)[:4], [1, 25, 49, 73])

down(101); press(step_xy(19)); up(101)                  # track 1 back to 1/16
r = play(24)
check('track 1 back at 1/16: pulses', r.get(1), [1, 7, 13, 19])
print('ratetest', 'PASS' if ok else 'FAIL')
