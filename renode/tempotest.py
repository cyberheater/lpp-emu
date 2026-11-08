#!/usr/bin/env python3
"""Tempo readout and tap tempo (Renode with run.resc, fresh flash).
1. Hold Shift: the note area shows the BPM (orange bar = hundreds, white tens and units). Default 120.
2. Shift + Up twice: 122.
3. Shift held, tap Sends/Tap 5 times 0.4 s apart (host time): the BPM becomes 60 / (0.4 s x the emulator's speed),
   measured from Renode's virtual clock during the taps."""
import os, re, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
from panel_bridge import LOGICAL_TO_CONTROL as L, HW_LED_TO_LOGICAL as H  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
leds = {}
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

for s, fn in ((panel, on_panel), (din, lambda ln: None), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.05)
def up(lg): panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.05)
def press(lg): down(lg); up(lg)

def monitor(cmd):
    m = socket.create_connection(('127.0.0.1', 1234)); m.settimeout(0.3)
    try:
        m.recv(4096)
    except OSError:
        pass
    m.sendall(f'mach set 0\n{cmd}\n'.encode())
    out, end = b'', time.time() + 2
    while time.time() < end:
        try:
            out += m.recv(65536)
        except OSError:
            if out:
                break
    m.close()
    return re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', out.decode(errors='replace'))

def shift(on):
    monitor(f'sysbus.gpioPortA OnGPIO 3 {"true" if on else "false"}'); time.sleep(0.3)

def vtime():
    v = re.search(r'Virtual Time: (\d+):(\d+):([\d.]+)', monitor('machine GetTimeSourceInfo'))
    return int(v[1]) * 3600 + int(v[2]) * 60 + float(v[3])

DIGITS = [[0b111, 0b101, 0b101, 0b111], [0b010, 0b110, 0b010, 0b111], [0b111, 0b011, 0b100, 0b111],
          [0b111, 0b011, 0b001, 0b111], [0b101, 0b101, 0b111, 0b001], [0b111, 0b110, 0b001, 0b111],
          [0b100, 0b111, 0b101, 0b111], [0b111, 0b001, 0b010, 0b010], [0b111, 0b111, 0b101, 0b111],
          [0b111, 0b101, 0b111, 0b001]]

def readout():
    """Decode the BPM from the note area LEDs (None if unreadable)."""
    time.sleep(0.3)
    with lock:
        px = {(c, r): leds.get((1 + (3 - r)) * 10 + c + 1) for c in range(8) for r in range(4)}
    white = lambda c: c is not None and min(c) > 150
    orange = lambda c: c is not None and c[0] > 150 and c[2] < 60
    hundreds = sum(orange(px[(0, r)]) for r in range(4))
    def digit(c0):
        rows = [sum(white(px[(c0 + x, r)]) << (2 - x) for x in range(3)) for r in range(4)]
        return DIGITS.index(rows) if rows in DIGITS else (0 if rows == [0, 0, 0, 0] else None)
    t, u = digit(1), digit(5)
    return None if t is None or u is None else hundreds * 100 + t * 10 + u

time.sleep(1.0)
press(97); time.sleep(0.5)
shift(True)
r1 = readout()
press(80); time.sleep(0.2); press(80)          # Shift + Up, twice
r2 = readout()
v0 = vtime(); t0 = time.time()
for _ in range(5):
    press(6); time.sleep(0.4 - 0.1)            # Sends/Tap
v1 = vtime(); t1 = time.time()
r3 = readout()
tap_led = leds.get(6)
shift(False)
speed = (v1 - v0) / (t1 - t0)
expect = 60 / (0.4 * speed)
print(f'readout on Shift: {r1} (expect 120); after Shift + Up x2: {r2} (expect 122)')
print(f'tap 5 x 0.4 s at {speed:.2f}x real time: readout {r3} (expect ~{expect:.0f}); Tap LED while Shift held {tap_led}')
ok = r1 == 120 and r2 == 122 and r3 is not None and abs(r3 - expect) <= 0.15 * expect
print('tempotest', 'PASS' if ok else 'FAIL')
