#!/usr/bin/env python3
"""Patterns button latch test (Renode with run.resc, fresh flash). Tap Patterns: the pattern view stays open (pattern 1
white); tapping pattern 2 switches to it and the view stays open; tapping Patterns closes it. Holding Patterns, tapping
pattern 1 and letting go switches back and closes the view."""
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
def pat_xy(p): return (8 - p // 8) * 10 + p % 8 + 1    # p: 0 = pattern 1 (top-left), 8 = pattern 9


def white(xy): c = leds.get(xy); return c is not None and min(c) >= 240

ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f'{label}: {got} (expect {want})', 'ok' if good else 'FAIL')

time.sleep(1.0)
press(97); time.sleep(0.5)
press(note_xy(12)); press(step_xy(1)); time.sleep(0.3)       # pattern 1: step 1 on
step1 = leds.get(step_xy(1))
press(89); time.sleep(0.4)                                   # tap: latch open
check('tap Patterns: view open, pattern 1 current', (white(pat_xy(0)), white(pat_xy(1))), (True, False))
press(pat_xy(1)); time.sleep(0.4)                            # pattern 2 (stopped: at once)
check('tap pattern 2: view still open, 2 current', (white(pat_xy(0)), white(pat_xy(1))), (False, True))
press(89); time.sleep(0.4)                                   # tap again: close
check('tap Patterns again: steps of empty pattern 2', (white(step_xy(1)), leds.get(step_xy(1)) == step1), (False, False))
down(89); time.sleep(0.3); press(pat_xy(0)); up(89); time.sleep(0.4)   # hold + pattern 1 + release
check('hold Patterns + pattern 1 + release: closed, pattern 1 steps', leds.get(step_xy(1)), step1)
press(89); time.sleep(0.4); press(89); time.sleep(0.4)       # open and close again
check('tap, tap: closed', leds.get(step_xy(1)), step1)
print('patlatchtest', 'PASS' if ok else 'FAIL')
