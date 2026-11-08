#!/usr/bin/env python3
"""Clock echo test (Renode with run.resc, fresh flash). Models a synth with MIDI Thru on DIN In: every real-time byte
(clock, start, stop) the sequencer sends on DIN Out 1 is sent straight back into DIN In. The sequencer must ignore its
own echo: the clock rate must stay the same as without the echo, and the Play LED must not turn orange (= following an
external clock)."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from panel_bridge import LOGICAL_TO_CONTROL as L, HW_LED_TO_LOGICAL as H  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
leds, state = {}, {'echo': False, 'clocks': 0}
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
        b = int(f[2], 16)
        if b == 0xF8:
            state['clocks'] += 1
        if b >= 0xF8 and state['echo']:
            din.sendall(f'i {b:02x}\n'.encode())   # the synth's MIDI Thru

for s, fn in ((panel, on_panel), (din, on_din), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def press(lg):
    panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.15)
    panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.15)

def clocks_over(seconds):
    with lock:
        c0 = state['clocks']
    time.sleep(seconds)
    with lock:
        return state['clocks'] - c0

def cyan(c):   # following an external clock: Play is orange
    return c is not None and c[0] > 2 * c[2] and c[1] > 2 * c[2] and c[0] > c[1]

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
press(81); time.sleep(0.2)        # a step on track 1 (output DIN 1)
press(20); time.sleep(1.0)        # Play
plain = clocks_over(5)
with lock:
    state['echo'] = True
time.sleep(1.0)
echoed = clocks_over(5)
led = [leds.get(20) for _ in range(1)][0]
samples = []
for _ in range(10):
    time.sleep(0.1)
    samples.append(leds.get(20))
press(20)
print(f'clocks in 5 s: without echo {plain}, with echo {echoed} (should be about the same)')
print('Play LED while echoed:', set(samples), '(orange = following its own echo: wrong)')
ok = plain > 0 and abs(echoed - plain) <= max(3, plain // 10) and not any(cyan(c) for c in samples)
print('echotest', 'PASS' if ok else 'FAIL')
