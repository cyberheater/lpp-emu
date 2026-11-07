#!/usr/bin/env python3
"""Polyphonic steps test (Renode with run.resc, fresh flash). Track 1 (DIN 1), externally clocked.
1. Record armed: an 8-note chord (C4 D E F G A B C5) arrives on DIN In 1 pulse into step 3 (pulse 13) -> step 3
   holds all eight.
2. Step edit: hold step 9, tap note pads C4, E4, G4, then E4 again -> step 9 = C4 + G4.
Playback pass: the 8 notes at pulse ~12 (velocity 0x70, the loudest of the chord), C4 G4 at pulse ~48."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL as L  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
din_log = []
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

def on_din(ln):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o' and f[1] == '1':
        din_log.extend(expand(1, int(f[2], 16)))

for s, fn in ((din, on_din), (panel, lambda ln: None), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.15)
def up(lg): panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.15)
def press(lg): down(lg); up(lg)
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1
def step_xy(step): return (8 - step // 8) * 10 + step % 8 + 1

def run(pulses, events):
    """events: {pulse: callable}. Returns [(pulse, note, velocity)] note-ons seen on DIN 1."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(0.04)
    for n in range(pulses):
        if n in events:
            events[n]()
        usb.sendall(b'm 1ff80000\n'); time.sleep(0.04)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    out, n, i = [], 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x90 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i + 2] > 0:
                out.append((n, b[i + 1], b[i + 2]))
            i += 3
        else:
            i += 1
    return out

time.sleep(1.0)
press(97); time.sleep(0.5)
press(10); time.sleep(0.3)
run(96, {
    13: lambda: din.sendall(b'i 90 3c 50 90 3e 54 90 40 58 90 41 5c 90 43 60 90 45 64 90 47 70 90 48 68\n'),
    19: lambda: din.sendall(b'i 80 3c 00 80 3e 00 80 40 00 80 41 00 80 43 00 80 45 00 80 47 00 80 48 00\n'),
})
press(10); time.sleep(0.3)

down(step_xy(8))
for pad in (12, 16, 19, 16):
    press(note_xy(pad))
up(step_xy(8)); time.sleep(0.3)

p = run(96, {})
print('playback: DIN 1 note-ons (pulse, note, vel):', p)
chord = sorted(nt for (pl, nt, v) in p if 10 <= pl <= 14)
vels = {v for (pl, nt, v) in p if 10 <= pl <= 14}
edited = sorted(nt for (pl, nt, v) in p if 46 <= pl <= 50)
print('recorded chord at step 3:', chord, 'velocities', vels, '(expect [60, 62, 64, 65, 67, 69, 71, 72] {112})')
print('edited chord at step 9:', edited, '(expect [60, 67])')
ok = chord == [60, 62, 64, 65, 67, 69, 71, 72] and vels == {112} and edited == [60, 67]
print('chordtest', 'PASS' if ok else 'FAIL')
