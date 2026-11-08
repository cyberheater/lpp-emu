#!/usr/bin/env python3
"""Step velocity/gate test (Renode with run.resc, fresh flash.bin). Track 1 -> DIN 1.
Step 1: velocity 64 (right-column button 49), gate 2/8 (bottom button 2). Step 5: defaults (100, 4/8).
Step 9: tapped on, then tapped again without editing -> off. Clocked externally: FA + 96 x F8 over USB.
Gate is checked by counting clock pulses between each note's on and off on DIN 1."""
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
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(101); press(note_xy(1)); up(101)
press(note_xy(12))
down(step_xy(1)); time.sleep(0.3)
bar = [leds.get((8 - k) * 10 + 9) for k in range(8)]
press(49); press(2)
time.sleep(0.3)
gate_bar = [leds.get(n) for n in range(1, 9)]
up(step_xy(1))
press(step_xy(5))
press(step_xy(9)); press(step_xy(9))
time.sleep(0.4)
print('velocity bar while step 1 held (top..bottom):', bar[:3], '...')
print('gate bar after setting 2/8:', gate_bar[:3], '...')
print('step LEDs 1/5/9:', leds.get(step_xy(1)), leds.get(step_xy(5)), leds.get(step_xy(9)), '(dimmer, full, unlit)')
with lock:
    din_log.clear()
usb.sendall(b'm 1ffa0000\n'); time.sleep(0.03)
for i in range(48):
    usb.sendall(b'm 1ff80000\n'); time.sleep(0.05)
usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
with lock:
    b = list(din_log)
events, pulses = [], 0
i = 0
while i < len(b):
    v = b[i]
    if v == 0xF8:
        pulses += 1; i += 1; continue
    if 0x80 <= v <= 0x9F and i + 2 < len(b):
        kind = 'on' if (v & 0xF0) == 0x90 and b[i + 2] > 0 else 'off'
        events.append((pulses, kind, b[i + 1], b[i + 2])); i += 3; continue
    i += 1
print('events (pulse, kind, note, vel):', events)
ons = [e for e in events if e[1] == 'on']
for n, (p, _, note, vel) in enumerate(ons):
    off = next((e[0] for e in events if e[1] == 'off' and e[0] >= p and e[2] == note and events.index(e) > events.index(ons[n])), None)
    print(f'note at pulse {p}: velocity {vel}, gate {None if off is None else off - p} pulses')
