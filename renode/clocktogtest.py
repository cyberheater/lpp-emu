#!/usr/bin/env python3
"""Ignore-external-clock test (Renode with run.resc, fresh flash). Shift + Play toggles following an external clock.
1. Shift held: Play is cyan (follows). Shift + Play: orange (ignores); the Projects LED turns amber (unsaved setting).
2. Ignoring: FA + 96 x F8 into DIN In must not start the sequencer: no notes, nothing passed on to the DIN outs.
3. Play: the internal clock runs; external F8 pulses arriving meanwhile must not change its rate or turn Play cyan.
4. Shift + Play again: follows again (cyan), and an external FA + F8 run plays 4 notes as in dinintest."""
import os, re, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402
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
    if len(f) == 3 and f[0] == 'o':
        din_log.extend((int(f[1]), v) for v in expand(int(f[1]), int(f[2], 16)))

for s, fn in ((panel, on_panel), (din, on_din), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def down(lg): panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.08)
def up(lg): panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.08)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1

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

def led(i):
    time.sleep(0.2)
    with lock:
        return leds.get(i)

cyan = lambda c: c is not None and c[1] > 2 * c[0] and c[2] > 2 * c[0]
orange = lambda c: c is not None and c[0] > 150 and c[1] < c[0] and c[2] < 40
amber = lambda c: c is not None and c[0] > 150 and c[1] > 60 and c[2] < 40

def ext_run(pulses=96):
    din.sendall(b'i fa\n'); time.sleep(0.03)
    for _ in range(pulses):
        din.sendall(b'i f8\n'); time.sleep(0.03)
    time.sleep(0.2)
    din.sendall(b'i fc\n'); time.sleep(0.8)

def take():
    with lock:
        d = list(din_log); din_log.clear()
    d1 = [v for p, v in d if p == 1]
    notes = [d1[i + 1] for i in range(len(d1) - 2) if 0x90 <= d1[i] <= 0x9F and d1[i + 2] > 0]
    return notes, d1.count(0xF8), sum(1 for p, v in d if p == 2 and v == 0xF8)

time.sleep(1.0)
press(97); time.sleep(0.5)
down(101); press(note_xy(1)); up(101)          # track 1 -> DIN 1
press(note_xy(12))
for s in (1, 5, 9, 13):
    press(step_xy(s))
press(98); time.sleep(1.5)                     # save, so the Projects LED is green
proj_before = led(98)

shift(True)
follow_led = led(20)
press(20)                                      # Shift + Play: ignore external clock
ignore_led = led(20)
shift(False)
proj_after = led(98)
ok1 = cyan(follow_led) and orange(ignore_led) and amber(proj_after)
print(f'Shift held: Play {follow_led} (cyan = follow); after Shift + Play: {ignore_led} (orange = ignore); '
      f'Projects LED {proj_before} -> {proj_after} (amber = unsaved)', 'ok' if ok1 else 'FAIL')

take()
ext_run()
notes, c1, c2 = take()
ok2 = notes == [] and c1 == 0 and c2 == 0
print(f'ignoring, external FA + 96 F8: notes {notes} (expect []), clock out DIN 1 {c1} DIN 2 {c2} (expect 0)',
      'ok' if ok2 else 'FAIL')

press(20); time.sleep(1.0)                     # Play on the internal clock
take(); time.sleep(3.0); _, plain, _ = take()
stop = threading.Event()
def feeder():
    while not stop.is_set():
        din.sendall(b'i f8\n'); time.sleep(0.03)
threading.Thread(target=feeder, daemon=True).start()
time.sleep(0.5); take(); time.sleep(3.0); _, fed, _ = take()
samples = [led(20) for _ in range(5)]
stop.set(); time.sleep(0.2)
press(20); time.sleep(0.5)
ok3 = plain > 0 and abs(fed - plain) <= max(3, plain // 10) and not any(cyan(c) for c in samples)
print(f'internal clock in 3 s: {plain}; with external F8 arriving: {fed} (should match); Play LEDs {set(samples)}',
      'ok' if ok3 else 'FAIL')

shift(True)
press(20)                                      # follow again
back_led = led(20)
shift(False)
take()
ext_run()
notes, c1, c2 = take()
# 95 is accepted: when the emulator catches up after host lag, two of our pulses can land within the 6 ms clock-echo
# window and the second is dropped (seen in about one run in two here; dinintest checks the exact count).
ok4 = cyan(back_led) and notes == [60] * 4 and c1 >= 95 and c2 >= 95
print(f'following again: Play {back_led} (cyan); notes {notes} (expect 4 x 60), clock passed DIN 1 {c1} '
      f'DIN 2 {c2} (expect 96)', 'ok' if ok4 else 'FAIL')
print('clocktogtest', 'PASS' if ok1 and ok2 and ok3 and ok4 else 'FAIL')
