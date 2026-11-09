#!/usr/bin/env python3
"""Step copy test (Renode with run.resc, fresh flash). Track 1 -> DIN 1: step 1 = chord C4 + E4 with gate 3/8 and
velocity 80. Hold Duplicate, tap step 1 (lights cyan), tap steps 5, 9 and (page 2) 33: each must play the same chord
with the same length and velocity."""
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

def play(pulses, spacing=0.02):
    """Returns ([(pulse, note, velocity)] note-ons, [(pulse, note)] note-offs) on DIN 1."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(spacing)
    for n in range(pulses):
        usb.sendall(b'm 1ff80000\n'); time.sleep(spacing)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    ons, offs, n, i = [], [], 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x80 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i] >= 0x90 and b[i + 2] > 0:
                ons.append((n, b[i + 1], b[i + 2]))
            else:
                offs.append((n, b[i + 1]))
            i += 3
        else:
            i += 1
    return ons, offs

ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f'{label}: {got} (expect {want})', 'ok' if good else 'FAIL')

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(step_xy(1)); time.sleep(0.2)                       # step 1 on (C4), held:
press(note_xy(12)); press(note_xy(16))                  #   chord C4 + E4
press(3)                                                #   gate 3/8 (bottom row 3): 2.25 pulses, off a pulse boundary
press(59)                                               #   velocity 80 (right column, 4th from top)
up(step_xy(1)); time.sleep(0.2)
down(50)                                                # hold Duplicate (50)
press(step_xy(1)); time.sleep(0.3)
src_led = leds.get(step_xy(1))
press(step_xy(5)); press(step_xy(9))
press(92); time.sleep(0.2); press(step_xy(1)); press(91)   # page 2: step 33, back to page 1
up(50); time.sleep(0.3)
print('copied step while Duplicate held:', src_led, '(cyan)')
ok &= src_led is not None and src_led[0] < 40 and src_led[1] > 150 and src_led[2] > 150
down(30); press(92); press(step_xy(32)); press(91); up(30)  # Fixed Length on page 2: 64 steps
ons, offs = play(6 * 64 + 6)
by_step = {}
for p, note, vel in ons:
    by_step.setdefault((p - 1) // 6 + 1, []).append((note, vel))
check('steps that play (pulse -> step)', sorted(by_step), [1, 5, 9, 33, 65])
check('step 5 / 9 / 33 notes and velocity = step 1', [sorted(by_step.get(k, [])) for k in (5, 9, 33)], [sorted(by_step[1])] * 3)
def length(step):
    on = 1 + (step - 1) * 6
    return [p - on for p, note in offs if note == 60 and on <= p <= on + 6][:1]
lens = {k: length(k) for k in (1, 5, 9, 33)}
print('C4 length in pulses (gate 3/8 of a 6-pulse step = 2.25):', lens)
# Lengths are read in whole clock pulses: the copies must match each other exactly and step 1 within a pulse (the
# first step after Start is timed from the clock rate estimated before the run).
ok &= lens[1] != [] and lens[5] == lens[9] == lens[33] != [] and abs(lens[5][0] - lens[1][0]) <= 1
print('dupetest', 'PASS' if ok else 'FAIL')
