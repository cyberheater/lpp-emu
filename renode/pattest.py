#!/usr/bin/env python3
"""Patterns + chaining test (Renode with run.resc).
  pattest.py program  fresh flash: track 1 -> DIN 1; pattern A step 1 = C4, pattern B step 1 = E4; chain A-B;
                      copy B to C with Duplicate; play 32 externally clocked steps; save.
  pattest.py verify   after a Renode restart: check pattern lights (A/B chained, C has notes) and replay."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
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
        din_log.append(int(f[2], 16))

for s, fn in ((panel, on_panel), (din, on_din), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.1)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.1)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1
def pat_xy(track, p): return (8 - p) * 10 + track + 1      # p: 0 = A

def play_steps(n):
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(0.03)
    for _ in range(n * 6):
        usb.sendall(b'm 1ff80000\n'); time.sleep(0.02)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    return [b[i + 1] for i in range(len(b) - 2) if 0x90 <= b[i] <= 0x9F and b[i + 2] > 0]

def pattern_view():
    down(89); time.sleep(0.4)
    view = {chr(65 + p): leds.get(pat_xy(0, p)) for p in range(4)}
    up(89)
    return view

time.sleep(1.0)
press(97); time.sleep(0.5)
if sys.argv[1] == 'program':
    down(101); press(note_xy(1)); up(101)          # track 1 -> DIN 1
    press(note_xy(12)); press(step_xy(1))           # A: C4 on step 1
    down(89); press(pat_xy(0, 1)); up(89)           # switch to B (stopped -> immediate)
    press(note_xy(16)); press(step_xy(1))           # B: E4 on step 1
    down(89); down(pat_xy(0, 0)); press(pat_xy(0, 1)); up(pat_xy(0, 0)); up(89)   # chain A-B
    down(89); down(50); press(pat_xy(0, 2)); up(50); up(89)                        # copy current (A) to C
    print('pattern lights (A..D):', pattern_view())
    print('32 steps, DIN 1 notes:', play_steps(32), '(expect 60, 64)')
    press(98); time.sleep(0.6)
    print('Projects LED after save:', leds.get(98))
else:
    print('Projects LED on entry:', leds.get(98), '(green = loaded)')
    print('pattern lights (A..D):', pattern_view())
    print('32 steps, DIN 1 notes:', play_steps(32), '(expect 60, 64)')
