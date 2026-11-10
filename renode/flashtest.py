#!/usr/bin/env python3
"""Sequencer project save/load test. Run with Renode (run.resc) up.
  flashtest.py program   open sequencer, track 1 -> DIN 1, steps 1/5/9/13 = D4, Tap Projects (save to slot 1)
  flashtest.py verify    (after restarting Renode with the same flash.bin) open sequencer, check the pattern was
                         loaded, Play, and check D4 arrives on DIN 1."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL, HW_LED_TO_LOGICAL  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
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
    if len(f) == 5 and f[0] == 'l':
        lg = HW_LED_TO_LOGICAL.get(int(f[1]))
        if lg is not None:
            leds[lg] = tuple(map(int, f[2:]))

def on_din(ln):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o':
        din_log.extend((int(f[1]), v) for v in expand(int(f[1]), int(f[2], 16)))

threading.Thread(target=reader, args=(panel, on_panel), daemon=True).start()
threading.Thread(target=reader, args=(din, on_din), daemon=True).start()

def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.08)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.08)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1
def colour(lg): return leds.get(lg, (0, 0, 0))

time.sleep(1.0)
press(97)
time.sleep(0.8)
print('Projects LED on entry:', colour(98), '(green = saved / matches flash, amber = unsaved, off = no flash)')

if sys.argv[1] == 'program':
    down(101); press(note_xy(1)); up(101)          # track 1 -> DIN 1
    press(note_xy(14))                              # D4 = 48 + 14 = 62
    for s in (1, 5, 9, 13):
        press(step_xy(s))
    time.sleep(0.3)
    print('Projects LED after edits:', colour(98))
    press(98)                                       # save
    time.sleep(0.15)
    print('Projects LED right after save:', colour(98))
    time.sleep(0.8)
    print('Projects LED after save:', colour(98))
    down(98); time.sleep(0.3)
    print('projects 1-8 (top grid row) while Projects held:', [colour(step_xy(1 + i)) for i in range(8)])
    up(98)
else:
    print('step 1/5 LEDs (track colour = loaded):', colour(step_xy(1)), colour(step_xy(5)), ' step 2:', colour(step_xy(2)))
    with lock:
        din_log.clear()
    press(20); time.sleep(3.0); press(20); time.sleep(0.3)
    with lock:
        b = [v for p, v in din_log if p == 1]
    notes = [b[i + 1] for i in range(len(b) - 2) if 0x90 <= b[i] <= 0x9F and b[i + 2] > 0]
    print('DIN 1 note-ons after reload:', notes[:6])
