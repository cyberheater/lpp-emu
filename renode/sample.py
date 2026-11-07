#!/usr/bin/env python3
"""Statistical profiler for a running Renode machine: samples PC (and optionally a register) via the monitor.
usage: python3 sample.py [N] [elf]   -> histogram of functions, plus real-time ratio over the run."""
import collections, re, socket, subprocess, sys, time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
ELF = sys.argv[2] if len(sys.argv) > 2 else None
s = socket.create_connection(('127.0.0.1', int(__import__('os').environ.get('MONPORT', '1234'))), timeout=5)
buf = b''

def cmd(c, wait_for=rb'\(lppmk3\) ?$'):
    global buf
    s.sendall((c + '\n').encode())
    buf = b''
    end = time.time() + 3
    while time.time() < end:
        s.settimeout(0.05)
        try:
            buf += s.recv(65536)
        except socket.timeout:
            pass
        clean = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', buf).replace(b'\r', b'')
        if re.search(wait_for, clean.rstrip(b'\n') + b' ', re.M) and clean.count(b'\n') >= 1:
            break
    return re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', buf).decode(errors='replace')

time.sleep(0.3); s.recv(65536)
cmd('mach set 0')
def times():
    t = cmd('machine GetTimeSourceInfo')
    v = re.search(r'Virtual Time: (\d+):(\d+):([\d.]+)', t)
    h = re.search(r'Host Time: (\d+):(\d+):([\d.]+)', t)
    f = lambda m: int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    return f(v), f(h)
v0, h0 = times()
pcs = []
for _ in range(N):
    out = cmd('cpu PC')
    m = re.findall(r'0x[0-9A-Fa-f]{6,8}', out)
    if m:
        pcs.append(int(m[-1], 16))
v1, h1 = times()
print(f'virtual {v1 - v0:.3f}s over host {h1 - h0:.2f}s  ->  {((v1 - v0) / (h1 - h0)):.3f}x real time')

hist = collections.Counter(pcs)
if ELF:
    nm = subprocess.run(['/Library/Developer/CommandLineTools/usr/bin/llvm-nm', '-n', '--demangle', ELF],
                        capture_output=True, text=True).stdout.splitlines()
    syms = []
    for ln in nm:
        p = ln.split(' ', 2)
        if len(p) == 3 and p[1] in 'tTwW':
            syms.append((int(p[0], 16), p[2]))
    import bisect
    keys = [a for a, _ in syms]
    def name(pc):
        i = bisect.bisect_right(keys, pc) - 1
        return syms[i][1][:110] if i >= 0 else '?'
    by = collections.Counter()
    for pc, n in hist.items():
        by[name(pc)] += n
    for nme, n in by.most_common(15):
        print(f'{n:4d}  {nme}')
for pc, n in hist.most_common(10):
    print(f'{n:4d}  {pc:#010x}')
