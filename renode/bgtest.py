#!/usr/bin/env python3
"""Background playback test (Renode with run.resc running, fresh flash.bin recommended).
Programs track 1 -> DIN 1 (C4 on steps 1/5/9/13), plays, switches to note mode and checks that DIN 1 keeps playing,
note-mode pads still send USB notes and the Sequencer button is green; then returns and stops."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
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
        din_log.append((int(f[1]), int(f[2], 16)))

def on_usb(ln):
    if ln.startswith('m ') and not ln.endswith('f80000'):
        usb_log.append(ln[2:])

for s, fn in ((panel, on_panel), (din, on_din), (usb, on_usb)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.08)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.08)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

def din1_notes():
    with lock:
        b = [v for p, v in din_log if p == 1]
        din_log.clear()
    return [b[i + 1] for i in range(len(b) - 2) if 0x90 <= b[i] <= 0x9F and b[i + 2] > 0]

time.sleep(1.0)
press(97); time.sleep(0.5)
down(101); press(note_xy(1)); up(101)
press(note_xy(12))
for s in (1, 5, 9, 13):
    press(step_xy(s))
press(20)                                      # Play
time.sleep(1.5)
print('playing in sequencer, DIN 1 notes:', din1_notes())
press(94)                                      # Note mode
time.sleep(0.5)
with lock:
    usb_log.clear()
print('in note mode, Sequencer button:', leds.get(97))
down(44); time.sleep(0.2); up(44)              # play a pad in note mode
time.sleep(2.5)
print('in note mode, DIN 1 notes kept coming:', din1_notes())
with lock:
    print('in note mode, pad sent USB notes:', [p for p in usb_log if p[1] in '89'][:4])
press(97)                                      # back to the sequencer
time.sleep(1.0)
whites = [n for n in range(1, 17) if min(leds.get(step_xy(n), (0, 0, 0))) > 200]
print('back in sequencer, playhead at step(s):', whites, ' Play LED:', leds.get(20))
press(20)
time.sleep(0.5)
print('after stop, DIN 1 notes:', din1_notes()[-2:], ' (stop sent)')
