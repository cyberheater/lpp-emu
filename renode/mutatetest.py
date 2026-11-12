#!/usr/bin/env python3
"""Mutate test (Renode with run.resc, fresh flash). Track 1 -> DIN 1, 16 steps: odd steps on with notes 60-67.
Three taps of Mutation (39) rearrange the part (same notes, new arrangement; the button turns purple); a long press
(1 s) brings back the original arrangement exactly and the button goes back to dim."""
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

def one_pass():
    ons, offs = play(6 * 16 + 3)
    return [((p - 1) // 6 + 1, note) for p, note, vel in ons if p <= 6 * 16]

def purple(): c = leds.get(39); return c is not None and c[0] > 120 and c[2] > 120 and c[1] < 60

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(101); press(note_xy(1)); up(101)                       # track 1 -> DIN 1
for k, n in enumerate(range(1, 16, 2)):
    press(note_xy(12 + k)); press(step_xy(n))               # step n = note 60 + k
down(30); press(step_xy(16)); up(30)                        # 16 steps
orig = one_pass()
print('original:', orig)
check('Mutation button dim before', purple(), False)
for _ in range(3):
    press(39); time.sleep(0.2)
time.sleep(0.3)
check('Mutation button purple after taps', purple(), True)
mut = one_pass()
print('mutated: ', mut)
check('same notes after mutate', sorted(n for _, n in mut), sorted(n for _, n in orig))
check('arrangement changed', mut != orig, True)
down(39); time.sleep(1.0); up(39); time.sleep(0.5)          # long press: restore
check('Mutation button dim after restore', purple(), False)
check('long press restores the original', one_pass(), orig)
press(39); time.sleep(0.5)                                  # a tap after restoring mutates again
check('tap after restore mutates again', one_pass() != orig, True)
print('mutatetest', 'PASS' if ok else 'FAIL')
