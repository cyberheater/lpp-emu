#!/usr/bin/env python3
"""Transpose / swing / probability test (Renode with run.resc, fresh flash.bin). Track 1 -> DIN 1, externally
clocked (FA + F8s over USB). Note timing is measured in clock pulses on the DIN 1 byte stream."""
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
    """Returns [(pulse_number, note)] for every note-on on DIN 1."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(spacing)
    for _ in range(pulses):
        usb.sendall(b'm 1ff80000\n'); time.sleep(spacing)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    out, n, i = [], 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x90 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i + 2] > 0:
                out.append((n, b[i + 1]))
            i += 3
        else:
            i += 1
    return out

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(101); press(note_xy(1)); press(note_xy(22)); time.sleep(0.2)
tp_led = leds.get(note_xy(22)); up(101)                 # DIN 1, transpose +2
press(note_xy(12)); press(step_xy(1)); press(step_xy(2))
r = play(12)
print('transpose +2: notes', [n for _, n in r], '(expect 62, 62)  pad LED', tp_led)
print('swing 50 %: note-on pulses', [p for p, _ in r], '(second at 7 = straight)')
shift(True); time.sleep(0.2); swing_bar_before = leds.get(step_xy(26)); press(step_xy(26)); time.sleep(0.2)
swing_bar_after = leds.get(step_xy(26)); shift(False)          # swing 75 %
r = play(12, spacing=0.05)
print('swing 75 %: note-on pulses', [p for p, _ in r], '(second later, ~9-10)  bar LED pad 26:', swing_bar_before, '->', swing_bar_after)

down(60); press(101); up(60)                            # clear track 1 pattern
for s in range(1, 9):
    press(step_xy(s))
    down(step_xy(s)); shift(True); press(49); shift(False); up(step_xy(s))     # probability 50 %
down(step_xy(1)); shift(True); time.sleep(0.3)
prob_bar = [leds.get((8 - k) * 10 + 9) for k in range(8)]
shift(False); up(step_xy(1))
r = play(16 * 6 * 4, spacing=0.02)
print('probability 50 % on 8 steps x 4 loops:', len(r), 'of 32 played (expect roughly 16)')
print('probability bar (top..bottom):', prob_bar)
