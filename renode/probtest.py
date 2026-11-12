#!/usr/bin/env python3
"""Probability page test (Renode with run.resc, fresh flash). Track 1 -> DIN 1, 16 steps, steps 1, 2, 4 and 9 on.
Tap Probability (49): the top two rows are 16 levels (100 % ... 6 %), rows 3-6 the steps. Select step 2, tap level 9
-> 50 %; select step 9, tap level 16 -> 6 %; an off step can't be selected. Close the page; 10 passes: steps 1 and
4 play every time, step 2 about half the time, step 9 rarely."""
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

def gpio(pin, high):
    """Setup (PA2) and Shift (PA3) are GPIO inputs on the MK3, not part of the M0 frame."""
    m = socket.create_connection(('127.0.0.1', 1234)); m.settimeout(0.3)
    try:
        m.recv(4096)
    except OSError:
        pass
    m.sendall(f'mach set 0\nsysbus.gpioPortA OnGPIO {pin} {"true" if high else "false"}\n'.encode())
    time.sleep(0.3); m.close(); time.sleep(0.1)

def shift(on): gpio(3, on)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

def play(pulses, spacing=0.02):
    """Returns ([(pulse, note, velocity)] note-ons, [(pulse, note)] note-offs) on DIN 1."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(spacing)
    for n in range(pulses):
        usb.sendall(b'm 1ff80000\n'); time.sleep(spacing)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    ons, offs, n, i = [], [], 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x80 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i] >= 0x90 and b[i + 2] > 0:
                ons.append((n, b[i + 1], b[i + 2]))
            else:
                offs.append((n, b[i + 1]))
            i += 3
        else:
            i += 1
    return ons, offs


ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f'{label}: {got} (expect {want})', 'ok' if good else 'FAIL')

def lit(xy): c = leds.get(xy); return c is not None and max(c) > 100
def column(col): return [lit(r * 10 + col) for r in range(8, 0, -1)]   # top..bottom

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(101); press(note_xy(1)); up(101)                       # track 1 -> DIN 1
press(note_xy(12))
for n in (1, 2, 4, 9):
    press(step_xy(n))
down(30); press(step_xy(16)); up(30)                        # 16 steps
def pstep(n): i = n - 1; return (6 - i // 8) * 10 + i % 8 + 1   # step n on the probability page (rows 6-3)
def plevel(lv): i = lv - 1; return (8 - i // 8) * 10 + i % 8 + 1  # level 1-16 on the top two rows
def white(xy): c = leds.get(xy); return c is not None and min(c) >= 240

press(49); time.sleep(0.4)
check('Probability button lit cyan', (lambda c: c is not None and c[2] > 150 and c[0] < 60)(leds.get(49)), True)
check('no step selected: levels dim', any(lit(plevel(lv)) for lv in range(1, 17)), False)
check('step 1 lit, step 3 (off) not, bottom rows dark', (lit(pstep(1)), lit(pstep(3)), leds.get(11)), (True, False, (0, 0, 0)))
press(pstep(2)); time.sleep(0.3)
check('step 2 selected (white), its level 1 (100 %) white', (white(pstep(2)), white(plevel(1))), (True, True))
check('levels lit, 1 brighter than 16', sum(leds.get(plevel(2))) > sum(leds.get(plevel(16))) > 0, True)
press(plevel(9)); time.sleep(0.3)                            # 50 %
check('step 2 at level 9 (50 %)', (white(plevel(9)), white(plevel(1))), (True, False))
press(pstep(9)); time.sleep(0.3)
check('step 9 selected: level 1', (white(pstep(9)), white(pstep(2)), white(plevel(1))), (True, False, True))
press(plevel(16)); time.sleep(0.3)                           # 6 %
check('step 9 at level 16 (6 %)', white(plevel(16)), True)
press(pstep(3)); time.sleep(0.3)                             # off step: not selectable
check('off step 3 not selected (step 9 still)', (white(pstep(3)), white(pstep(9))), (False, True))
press(pstep(2)); time.sleep(0.3)
check('back on step 2: level 9', white(plevel(9)), True)
press(pstep(1)); time.sleep(0.3)                             # select step 1 so step 2 is not white
check('step 2 (50 %) dimmer than step 4 (100 %)', sum(leds.get(pstep(2))) < sum(leds.get(pstep(4))), True)
press(49); time.sleep(0.4)
check('closed: step 1 pad lit again, step 3 not', (lit(step_xy(1)), lit(step_xy(3))), (True, False))
ons, offs = play(6 * 16 * 10 + 3)
hits = {}
for p, note, vel in ons:
    if p > 6 * 16 * 10:
        continue                                            # past the 10 passes (the extra pulses)
    st = (p - 1) // 6 % 16 + 1
    hits[st] = hits.get(st, 0) + 1
print('plays per step over 10 passes:', dict(sorted(hits.items())))
check('steps 1 and 4 every pass', (hits.get(1), hits.get(4)), (10, 10))
check('step 2 (50 %) sometimes', 1 <= hits.get(2, 0) <= 9, True)
check('step 9 (6 %) rarely', hits.get(9, 0) <= 4, True)
print('probtest', 'PASS' if ok else 'FAIL')
