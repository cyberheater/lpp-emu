#!/usr/bin/env python3
"""Step recording test (Renode with run.resc, fresh flash). Track 1 -> DIN 1, pattern length 8. Record armed while
stopped; a keyboard on DIN In plays C4, E4, then G4 + B4 together (a chord on step 3); tapping step 5 skips step 4;
then D4, F4, A4, C5 fill steps 5-8, after which Record disarms. Playback must give exactly those notes on those steps."""
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

def white(xy): c = leds.get(xy); return c is not None and min(c) >= 240

def key(*notes, vel=90):
    din.sendall(('i ' + ' '.join(f'90 {n:02x} {vel:02x}' for n in notes) + '\n').encode()); time.sleep(0.25)
    din.sendall(('i ' + ' '.join(f'80 {n:02x} 00' for n in notes) + '\n').encode()); time.sleep(0.25)

time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external; follow_external(press)   # follow the external clock this test sends
down(30); press(step_xy(8)); up(30)                     # Fixed Length: 8 steps
rec_off = leds.get(10)
press(10); time.sleep(0.3)                              # arm Record while stopped: step recording
check('cursor on step 1', white(step_xy(1)), True)
key(0x3c); key(0x40); key(0x43, 0x47)
time.sleep(0.3)
check('cursor on step 4 after three entries', white(step_xy(4)), True)
press(step_xy(5)); time.sleep(0.3)                      # skip step 4
check('cursor moved to step 5', white(step_xy(5)), True)
key(0x3e); key(0x41); key(0x45); key(0x48)
time.sleep(0.3)
check('Record disarmed after step 8', leds.get(10), rec_off)
key(0x30)                                               # not recorded any more
ons, offs = play(6 * 8 + 3)
by_step = {}
for p, note, vel in ons:
    by_step.setdefault((p - 1) // 6 + 1, []).append(note)
check('notes per step', {k: sorted(v) for k, v in by_step.items() if k <= 8},
      {1: [60], 2: [64], 3: [67, 71], 5: [62], 6: [65], 7: [69], 8: [72]})
check('velocity recorded', sorted({v for _, _, v in ons}), [90])
print('steprectest', 'PASS' if ok else 'FAIL')
