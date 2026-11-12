#!/usr/bin/env python3
"""Count-in test (Renode with run.resc, fresh flash, internal clock). Record Arm (bottom row 1) lights with Record;
armed + Play: the grid flashes red 4 times
before any MIDI clock goes out, and a note pad tapped during the count-in is not recorded. Then the count-in is
switched off on the Setup page (pad 21): Record + Play starts at once, with no red flashes."""
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

def red(xy): c = leds.get(xy); return c is not None and c[0] > 200 and c[1] < 60 and c[2] < 60
def clocks():
    with lock:
        return sum(1 for b in din_log if b == 0xF8)

def watch(secs):
    """Samples the grid and DIN 1 clock: returns (red flashes seen before the first clock, clocks at the end)."""
    flashes, was, t_end = 0, False, time.time() + secs
    while time.time() < t_end:
        r = red(44) and red(81) and red(18)
        if r and not was and clocks() == 0:
            flashes += 1
        was = r
        time.sleep(0.02)
    return flashes, clocks()

time.sleep(1.0)
press(97); time.sleep(0.5)
down(101); press(note_xy(1)); up(101)                       # track 1 -> DIN 1
press(1); time.sleep(0.3)                                   # arm with Record Arm (bottom row, first button)
check('Record Arm and Record lit when armed', (leds.get(1), leds.get(10)), ((160, 0, 0), (160, 0, 0)))
with lock:
    din_log.clear()
press(20)                                                   # Play: count-in
time.sleep(0.6); press(note_xy(12))                         # a note during the count-in: not recorded
flashes, n = watch(4.0)
check('red flashes before the clock starts', flashes >= 3, True)   # the first may start before sampling
print('flashes seen:', flashes, ' clocks after:', n)
check("clock running after the count-in", n > 12, True)
press(20); time.sleep(0.4)                                  # stop
press(10); time.sleep(0.3)                                  # disarm Record
check('Record Arm dim when disarmed', leds.get(1), (32, 0, 0))
check('note played during the count-in not recorded (step 1 off)', red(step_xy(1)) or (lambda c: c is not None and max(c) > 100)(leds.get(step_xy(1))), False)
gpio(2, True); time.sleep(0.3); gpio(2, False); time.sleep(0.8)   # Setup
on = leds.get(21)
press(21); time.sleep(0.3)
off = leds.get(21)
print('Setup pad 21 before / after tap:', on, off)
check('Setup pad 21 bright then dim', (on is not None and on[0] > 200, off is not None and off[0] < 100), (True, True))
gpio(2, True); time.sleep(0.3); gpio(2, False); time.sleep(1.0)   # leave Setup
press(97); time.sleep(0.5)
press(10); time.sleep(0.3)
with lock:
    din_log.clear()
press(20)
flashes, n = watch(1.0)
check('count-in off: no red flashes', flashes, 0)
check('count-in off: clock starts at once', n > 12, True)
press(20); time.sleep(0.3)
print('counttest', 'PASS' if ok else 'FAIL')
