#!/usr/bin/env python3
"""Live recording test (Renode with run.resc, fresh flash). Track 1 (DIN 1 by default), externally clocked.
Pass 1 (Record armed): pad C4 pressed 1 pulse into step 3 (pulse 13) and held ~6 pulses -> step 3, long gate;
keyboard E4 on DIN In 4 pulses into step 9 (pulse 52), held 2 pulses -> step 10 (late), not replayed in pass 1.
Pass 2 (Record off): both notes must play: C4 at pulse ~12, E4 at pulse ~54."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL as L, HW_LED_TO_LOGICAL as H  # noqa: E402

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
    if len(f) == 5 and f[0] == 'l' and H.get(int(f[1])) is not None:
        leds[H[int(f[1])]] = tuple(map(int, f[2:]))

def on_din(ln):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o' and f[1] == '1':
        din_log.extend(expand(1, int(f[2], 16)))

for s, fn in ((panel, on_panel), (din, on_din), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.1)
def up(lg): panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.1)
def press(lg): down(lg); up(lg)
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

offs = []   # (pulse, note) note-offs seen by the last run()

def run(pulses, events):
    """events: {pulse: callable}. Returns [(pulse, note, velocity)] note-ons seen on DIN 1."""
    offs.clear()
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
            else:
                offs.append((n, b[i + 1]))
            i += 3
        elif 0x80 <= b[i] <= 0x8F and i + 2 < len(b):
            offs.append((n, b[i + 1]))
            i += 3
        else:
            i += 1
    return out

time.sleep(1.0)
press(97); time.sleep(0.5)
press(10); time.sleep(0.3)
print('Record LED armed (dark red expected):', leds.get(10))
pad_c4 = L[note_xy(12)]
p1 = run(96, {
    13: lambda: panel.sendall(f'p {pad_c4} 2400\n'.encode()),
    19: lambda: panel.sendall(f'p {pad_c4} 0\n'.encode()),
    52: lambda: din.sendall(b'i 90 40 50\n'),
    54: lambda: din.sendall(b'i 80 40 00\n'),
})
print('pass 1 (recording): DIN 1 note-ons (pulse, note, vel):', p1, '(C4 preview live; E4 not replayed)')
press(10); time.sleep(0.3)
print('Record LED disarmed:', leds.get(10))
p2 = run(96, {})
print('pass 2 (playback): DIN 1 note-ons:', p2, '(expect 60 at ~12, 64 at ~54)')

# A keyboard note held for 4 steps (24 pulses) is recorded with that length, not cut to one step.
press(10); time.sleep(0.3)
run(96, {
    28: lambda: din.sendall(b'i 90 43 50\n'),
    52: lambda: din.sendall(b'i 80 43 00\n'),
})
press(10); time.sleep(0.3)
p3 = run(96, {})
on = [n for n, note, _ in p3 if note == 0x43]
off = [n for n, note in offs if note == 0x43 and on and n > on[0]]
held = off[0] - on[0] if on and off else None
print('held note (G4, 24 pulses = 4 steps): on at', on, 'off at', off[:1], '-> length', held, 'pulses (expect ~24, not 6)')
print('rectest long note', 'PASS' if held is not None and 21 <= held <= 26 else 'FAIL')
