#!/usr/bin/env python3
"""MIDI thru test (Renode with run.resc, fresh flash). Track 3 selected (channel 3, DIN 1 by default).
A keyboard on DIN In, channel 1, must play the selected track: its notes and controllers come out of DIN 1 on
channel 3. Echoes (the same note-on again while held, the same controller again at once) must be dropped."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midistream import expand  # noqa: E402  (DIN outs use running status)
from panel_bridge import LOGICAL_TO_CONTROL as L  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
usb = socket.create_connection(('127.0.0.1', 3457))
din = socket.create_connection(('127.0.0.1', 3458))
out = {1: [], 2: []}
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

def on_din(ln):
    f = ln.split()
    if len(f) == 3 and f[0] == 'o':
        out[int(f[1])].extend(expand(int(f[1]), int(f[2], 16)))

for s, fn in ((din, on_din), (panel, lambda ln: None), (usb, lambda ln: None)):
    threading.Thread(target=reader, args=(s, fn), daemon=True).start()

def press(lg):
    panel.sendall(f'p {L[lg]} 2800\n'.encode()); time.sleep(0.15)
    panel.sendall(f'p {L[lg]} 0\n'.encode()); time.sleep(0.15)

def messages(port):
    """Channel messages (status, data...) on a DIN out, real-time bytes left out."""
    with lock:
        b = [x for x in out[port] if x < 0xF8]
    msgs, i = [], 0
    while i < len(b):
        if b[i] >= 0x80:
            n = 2 if b[i] & 0xF0 in (0xC0, 0xD0) else 3
            msgs.append(tuple(b[i:i + n])); i += n
        else:
            i += 1
    return msgs

def step(label, data, expect):
    with lock:
        out[1].clear(); out[2].clear()
    din.sendall(('i ' + data + '\n').encode()); time.sleep(0.6)
    got = [tuple(f'{x:02x}' for x in m) for m in messages(1)]
    ok = got == expect
    print(f'{label}: DIN 1 {got} (expect {expect})', 'ok' if ok else 'WRONG')
    return ok

time.sleep(1.0)
press(97); time.sleep(0.5)    # sequencer
press(103); time.sleep(0.3)   # select track 3
results = [
    step('note-on ch 1', '90 3c 64', [('92', '3c', '64')]),
    step('echo of it', '92 3c 64', []),
    # a keyboard's echo comes straight back (milliseconds), so send the wheel move and its echo together
    step('mod wheel + its echo', 'b0 01 40 b2 01 40', [('b2', '01', '40')]),
    step('mod wheel moved', 'b0 01 41', [('b2', '01', '41')]),
    step('note-off', '80 3c 00', [('92', '3c', '00')]),
    step('echo of the off', '92 3c 00', []),
]
print('thrutest', 'PASS' if all(results) else 'FAIL')
