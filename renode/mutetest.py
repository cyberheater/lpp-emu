#!/usr/bin/env python3
"""Mute / solo test (Renode with run.resc, fresh flash). Tracks 1 and 2 -> DIN 1 (channels 1, 2), notes on steps
1, 5, 9, 13 of a 16-step pattern, externally clocked. Mute / Solo (bottom row 2 / 3) arm a mode in which the track
buttons mute / solo at once; Shift + Mute queues the change until the track's pattern next starts."""
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

def play(pulses, events={}, spacing=0.02):
    """Returns {channel: [pulse_number, ...]} for every note-on on DIN 1; events: {pulse: callable}."""
    with lock:
        din_log.clear()
    usb.sendall(b'm 1ffa0000\n'); time.sleep(spacing)
    for n in range(pulses):
        if n in events:
            events[n]()
        usb.sendall(b'm 1ff80000\n'); time.sleep(spacing)
    usb.sendall(b'm 1ffc0000\n'); time.sleep(0.8)
    with lock:
        b = list(din_log)
    out, n, i = {}, 0, 0
    while i < len(b):
        if b[i] == 0xF8:
            n += 1; i += 1
        elif 0x90 <= b[i] <= 0x9F and i + 2 < len(b):
            if b[i + 2] > 0:
                out.setdefault((b[i] & 15) + 1, []).append(n)
            i += 3
        else:
            i += 1
    return out

ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f'{label}: {got} (expect {want})', 'ok' if good else 'FAIL')

LOOP = [1, 25, 49, 73]
time.sleep(1.0)
press(97); time.sleep(0.5)
from seqhelp import follow_external, shift_gpio; follow_external(press)   # follow the external clock this test sends
for s in (1, 5, 9, 13):                                 # track 1: C4
    press(step_xy(s))
press(102); press(note_xy(16))                          # track 2: E4
for s in (1, 5, 9, 13):
    press(step_xy(s))
press(101)

press(2); time.sleep(0.2)                               # Mute armed: the button flashes
flashes = set()
for _ in range(8):
    flashes.add(leds.get(2)); time.sleep(0.07)
press(101); time.sleep(0.3)                             # mute track 1
mute_mode_led = leds.get(101)
print('Mute button while armed:', flashes, ' track 1 button while muted (mute mode):', mute_mode_led)
ok &= len(flashes) >= 2 and all(c[0] > c[1] and c[0] > c[2] for c in flashes if c) and mute_mode_led[0] > mute_mode_led[1]
press(2)                                                # disarm
r = play(96)
check('track 1 muted: channel 1 / channel 2', (r.get(1), r.get(2)), (None, LOOP))

press(2); press(101); press(2)                          # unmute track 1 (tap a muted track in mute mode)
r = play(96)
check('track 1 unmuted: channel 1 / channel 2', (r.get(1), r.get(2)), (LOOP, LOOP))

press(3); press(102); press(3)                          # solo track 2
r = play(96)
check('track 2 soloed: channel 1 / channel 2', (r.get(1), r.get(2)), (None, LOOP))
press(3); press(102); press(3)                          # unsolo

shift_gpio(True); press(2); shift_gpio(False); time.sleep(0.8)    # Shift + Mute: queued mute mode
queued_flash = set()
for _ in range(8):
    queued_flash.add(leds.get(2)); time.sleep(0.07)
print('Mute button in queued mode (red / white):', queued_flash)
ok &= (252, 252, 252) in queued_flash
r = play(192, {30: lambda: panel.sendall(f'p {LOGICAL_TO_CONTROL[101]} 2800\n'.encode()),
               32: lambda: panel.sendall(f'p {LOGICAL_TO_CONTROL[101]} 0\n'.encode())})
check('queued mute of track 1 at pulse 30: channel 1 (plays out the loop)', r.get(1), LOOP)
check('channel 2 unaffected', r.get(2), LOOP + [p + 96 for p in LOOP])
press(2)                                                # disarm
print('mutetest', 'PASS' if ok else 'FAIL')
