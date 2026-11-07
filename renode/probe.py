#!/usr/bin/env python3
"""Fast repeated reads through the Renode monitor.
usage: probe.py N 'sysbus ReadByte 0x2004924f' 'sysbus ReadDoubleWord 0x40026010' ...
Prints one line per round with every command's hex result."""
import re, socket, sys, time

n = int(sys.argv[1]); cmds = sys.argv[2:]
s = socket.create_connection(('127.0.0.1', int(__import__('os').environ.get('MONPORT', '1234'))), timeout=5)
s.settimeout(0.5)
buf = b''
def until_prompt():
    global buf
    end = time.time() + 2
    while time.time() < end:
        try:
            buf += s.recv(65536)
        except socket.timeout:
            pass
        clean = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', buf)
        if clean.rstrip().endswith(b')'):
            out = clean; buf = b''
            return out.decode(errors='replace')
    out = buf; buf = b''
    return re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', out).decode(errors='replace')
until_prompt()
s.sendall(b'mach set 0\n'); until_prompt()
for _ in range(n):
    row = []
    for c in cmds:
        s.sendall((c + '\n').encode())
        out = until_prompt()
        m = re.findall(r'0x[0-9A-Fa-f]+', out.split('\n', 1)[-1])
        row.append(m[-1] if m else '?')
    print(time.strftime('%H:%M:%S'), ' '.join(row), flush=True)
