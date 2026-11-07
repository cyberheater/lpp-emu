#!/usr/bin/env python3
"""External clock test (Renode with run.resc, fresh flash.bin). Programs track 1 -> DIN 1 (C4, steps 1/5/9/13), then
sends FA + 96 x F8 + FC into the USB MIDI port (cable 1). Expects exactly 4 notes on DIN 1 (one per 24 pulses),
the 96 pulses passed through to both DIN outs, and no clock echoed back to USB."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL, HW_LED_TO_LOGICAL  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
leds, din_log, usb_log = {}, [], []
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
    if len(f) == 3 and f[0] == 'o':
        din_log.extend((int(f[1]), v) for v in expand(int(f[1]), int(f[2], 16)))

def on_usb(ln):
    if ln.startswith('m '):
        usb_log.append(ln[2:])

for s, fn in ((panel, on_panel), (din, on_din), (usb, on_usb)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.08)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.08)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

time.sleep(1.0)
press(97); time.sleep(0.5)
down(101); press(note_xy(1)); up(101)
press(note_xy(12))
for s in (1, 5, 9, 13):
    press(step_xy(s))
time.sleep(0.5)
with lock:
    din_log.clear(); usb_log.clear()

usb.sendall(b'm 1ffa0000\n'); time.sleep(0.03)
for i in range(96):
    usb.sendall(b'm 1ff80000\n'); time.sleep(0.03)
    if i == 40:
        play_led = leds.get(20)
time.sleep(0.2)
usb.sendall(b'm 1ffc0000\n')
time.sleep(1.0)

with lock:
    d1 = [v for p, v in din_log if p == 1]
    d2 = [v for p, v in din_log if p == 2]
    ulog = list(usb_log)
notes = [d1[i + 1] for i in range(len(d1) - 2) if 0x90 <= d1[i] <= 0x9F and d1[i + 2] > 0]
print('Play LED while following external clock (cyan expected):', play_led)
print('DIN 1 note-ons:', notes, '(expect 4 x 60)')
print('clock passed through: DIN 1', d1.count(0xF8), 'DIN 2', d2.count(0xF8), '(expect 96 each)',
      ' start/stop on DIN 1:', [hex(v) for v in d1 if v in (0xFA, 0xFC)])
print('clock echoed to USB:', sum(1 for p in ulog if p[2:4] == 'f8'), '(expect 0)')
time.sleep(0.8)
print('Play LED after clock stopped (back to internal, grey):', leds.get(20))
