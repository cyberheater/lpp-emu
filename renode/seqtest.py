#!/usr/bin/env python3
"""End-to-end test of the CoreFW step sequencer in the emulator (Renode started with run.resc).

Drives the front panel (3456), listens to USB MIDI (3457) and DIN (3458):
  track 1 -> DIN 1, steps 1,5,9,13 note C4;  track 2 -> DIN 2, steps 3,7,11,15 note E4 (chosen on the note pads);
  then Play for ~4 s and check what arrives on each port and how evenly the beats are spaced."""
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
        t = time.time()
        with lock:
            for ln in lines:
                fn(ln.decode(), t)

def on_panel(ln, t):
    f = ln.split()
    if len(f) == 5 and f[0] == 'l':
        lg = HW_LED_TO_LOGICAL.get(int(f[1]))
        if lg is not None:
            leds[lg] = tuple(map(int, f[2:]))

def on_din(ln, t):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o':
        din_log.append((t, int(f[1]), int(f[2], 16)))

def on_usb(ln, t):
    if ln.startswith('m '):
        usb_log.append((t, ln[2:]))

for s, fn in ((panel, on_panel), (din, on_din), (usb, on_usb)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def press(logical, hold=0.08):
    ctrl = LOGICAL_TO_CONTROL[logical]
    panel.sendall(f'p {ctrl} 2800\n'.encode()); time.sleep(hold)
    panel.sendall(f'p {ctrl} 0\n'.encode()); time.sleep(0.08)

def down(logical): panel.sendall(f'p {LOGICAL_TO_CONTROL[logical]} 2800\n'.encode()); time.sleep(0.08)
def up(logical): panel.sendall(f'p {LOGICAL_TO_CONTROL[logical]} 0\n'.encode()); time.sleep(0.08)

def step_xy(n):  # step 1..32
    i = n - 1
    return (8 - i // 8) * 10 + i % 8 + 1

def note_xy(pad):  # pad 0..31, note = base(48) + pad
    return (1 + pad // 8) * 10 + pad % 8 + 1

time.sleep(1.0)
press(97)                                   # Sequencer button
time.sleep(0.5)
ok_enter = min(leds.get(97, (0, 0, 0))) > 200
print('sequencer opened:', ok_enter, ' track-1 button colour', leds.get(101))

def setup_track(track_btn, output_pad, note_pad, steps):
    down(track_btn); press(note_xy(output_pad)); up(track_btn)   # hold track + output pad
    press(note_xy(note_pad))                                       # choose note
    for s in steps:
        press(step_xy(s))

setup_track(101, 1, 12, [1, 5, 9, 13])      # track 1 -> DIN 1, C4 (48+12=60)
setup_track(102, 2, 16, [3, 7, 11, 15])     # track 2 -> DIN 2, E4 (64)
time.sleep(0.3)
print('step 1 lit with track-2 view?', leds.get(step_xy(3)), ' track-2 button', leds.get(102))
with lock:
    din_log.clear(); usb_log.clear()
press(20)                                   # Play
time.sleep(4.0)
press(20)                                   # Stop
time.sleep(0.3)

with lock:
    log = list(din_log); ulog = list(usb_log)
for port in (1, 2):
    b = [x for x in log if x[1] == port]
    clocks = sum(1 for x in b if x[2] == 0xF8)
    notes = [(t, b[i + 1][2], b[i + 2][2]) for i, (t, p, v) in enumerate(b[:-2]) if 0x90 <= v <= 0x9F and b[i + 1][2] < 0x80]
    ons = [(t, n) for t, n, vel in notes if vel > 0]
    gaps = [round(ons[i + 1][0] - ons[i][0], 3) for i in range(len(ons) - 1)]
    print(f'DIN {port}: {clocks} clocks, note-ons {[n for _, n in ons][:8]}, gaps(s) {gaps[:8]}, start/stop',
          [hex(x[2]) for x in b if x[2] in (0xFA, 0xFC)])
offs = [x for x in log if 0x80 <= x[2] <= 0x8F]
print('note-off status bytes seen:', len(offs))
print('USB packets (non-clock):', [p for _, p in ulog if not p.endswith('f80000')][:6], ' clock packets', sum(1 for _, p in ulog if p.endswith('f80000')))
