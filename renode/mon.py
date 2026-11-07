#!/usr/bin/env python3
"""Send commands to the Renode telnet monitor and print the replies.
usage: python3 mon.py "cpu PC" "sysbus FindSymbolAt `cpu PC`" ..."""
import re, socket, sys, time

s = socket.create_connection(('127.0.0.1', int(sys.argv[1]) if sys.argv[1:2] and sys.argv[1].isdigit() else 1234), timeout=5)
cmds = [a for a in sys.argv[1:] if not a.isdigit()]
out = b''
def drain(t):
    global out
    end = time.time() + t
    s.settimeout(0.2)
    while time.time() < end:
        try:
            d = s.recv(65536)
            if not d:
                break
            out += d
        except socket.timeout:
            pass
drain(0.5)
for c in cmds:
    s.sendall((c + '\n').encode())
    drain(1.0)
s.close()
txt = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', out).decode(errors='replace')
txt = re.sub(r'[\x00-\x08\x0e-\x1f\xff\xfb\xfd]', '', txt)
print('\n'.join(l for l in txt.replace('\r', '').split('\n') if l.strip()))
