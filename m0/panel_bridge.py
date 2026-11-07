#!/usr/bin/env python3
"""Web front panel for the Launchpad Pro MK3 emulator.

The M0 co-processor itself is modelled inside Renode (renode/LPPM0.cs). This script bridges its
front-panel socket (default localhost:3456, text lines) to the browser panel on http://localhost:8765,
and drives the Setup (PA2) / Shift (PA3) GPIO pins through the Renode monitor (default localhost:1234).
"""
import argparse, json, os, queue, socket, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- maps copied from CoreFW src/sys/driver/launchpad-pro-mk3/map.rs (GPL-3.0) ----
BUTTON_REMAP = [
    11, 21, 31, 41, 51, 61, 71, 81, 12, 22, 32, 42, 52, 62, 72, 82, 13, 23, 33, 43, 53, 63, 73, 83,
    14, 24, 34, 44, 54, 64, 74, 84, 15, 25, 35, 45, 55, 65, 75, 85, 16, 26, 36, 46, 56, 66, 76, 86,
    17, 27, 37, 47, 57, 67, 77, 87, 18, 28, 38, 48, 58, 68, 78, 88, 91, 92, 80, 70, 60, 50, 40, 30,
    20, 10, 101, 1, 0, 0, 0, 90, 93, 94, 0, 0, 0, 0, 102, 2, 103, 3, 104, 4, 0, 0, 0, 0, 95, 96, 0,
    0, 0, 0, 105, 5, 106, 6, 107, 7, 0, 0, 0, 0, 97, 98, 89, 79, 69, 59, 49, 39, 29, 19, 108, 8, 0,
    0, 0, 0,
]
LED_REMAP = [
    53, 26, 50, 51, 52, 77, 78, 79, 107, 0xFF, 23, 24, 44, 45, 46, 71, 72, 73, 104, 105, 21, 22,
    41, 42, 43, 68, 69, 70, 102, 103, 18, 19, 20, 39, 40, 66, 67, 99, 100, 101, 15, 16, 17, 37, 38,
    64, 65, 96, 97, 98, 12, 13, 14, 35, 36, 62, 63, 93, 94, 95, 9, 10, 11, 33, 34, 60, 61, 90, 91,
    92, 6, 7, 8, 31, 32, 58, 59, 87, 88, 89, 3, 4, 5, 29, 30, 56, 57, 84, 85, 86, 0, 1, 2, 27, 28,
    54, 55, 81, 82, 83, 0xFF, 25, 47, 48, 49, 74, 75, 76, 106, 0xFF,
]
LOGICAL_TO_CONTROL = {}
for ctrl, logical in enumerate(BUTTON_REMAP):
    if logical or ctrl == 78:
        LOGICAL_TO_CONTROL[logical] = ctrl
HW_LED_TO_LOGICAL = {hw: lg for lg, hw in enumerate(LED_REMAP) if hw != 0xFF}
SETUP_LOGICAL, SHIFT_LOGICAL = 0, 90


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.leds = {}                          # logical -> [r,g,b]
        self.listeners = []                     # SSE queues
        self.stats = {}

    def publish(self, msg):
        data = json.dumps(msg)
        for q in list(self.listeners):
            try:
                q.put_nowait(data)
            except queue.Full:
                pass


class PanelLink:
    """Connection to the M0 model's front-panel socket inside Renode."""
    def __init__(self, port, state, log):
        self.addr, self.state, self.log = ('127.0.0.1', port), state, log
        self.sock = None
        self.lock = threading.Lock()

    def send(self, line):
        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall(line.encode())
                except OSError:
                    pass

    def press(self, logical, down, pressure):
        ctrl = LOGICAL_TO_CONTROL.get(logical)
        if ctrl is not None:
            self.send(f'p {ctrl} {pressure if down else 0}\n')

    def run(self):
        while True:
            try:
                s = socket.create_connection(self.addr, timeout=2)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(None)
                self.sock = s
                with self.state.lock:
                    self.state.leds = {lg: [0, 0, 0] for lg in self.state.leds}
                self.log(f'connected to M0 panel socket {self.addr}')
                self.state.publish({'link': True, 'leds': self.state.leds})
                buf = b''
                while True:
                    d = s.recv(65536)
                    if not d:
                        break
                    buf += d
                    *lines, buf = buf.split(b'\n')
                    changed = {}
                    for ln in lines:
                        f = ln.decode().split()
                        if not f:
                            continue
                        if f[0] == 'l' and len(f) == 5:
                            lg = HW_LED_TO_LOGICAL.get(int(f[1]))
                            if lg is not None:
                                changed[lg] = [int(f[2]), int(f[3]), int(f[4])]
                        elif f[0] == 's':
                            k = ('frames', 'pings', 'led_commits', 'overruns', 'unknown', 'streaming')
                            self.state.stats = dict(zip(k, map(int, f[1:])))
                        elif f[0] == 'up':
                            self.log('button stream up')
                    if changed:
                        with self.state.lock:
                            self.state.leds.update(changed)
                        self.state.publish({'leds': changed})
            except OSError:
                pass
            self.sock = None
            self.state.publish({'link': False})
            time.sleep(0.5)


class Monitor:
    """Renode monitor socket (one client at a time: connect, send, close)."""
    def __init__(self, port, log):
        self.addr, self.log = ('127.0.0.1', port), log

    def cmd(self, line):
        def run():
            try:
                with socket.create_connection(self.addr, timeout=2) as s:
                    s.settimeout(0.3)
                    try:
                        s.recv(65536)
                    except OSError:
                        pass
                    s.sendall(b'mach set 0\n' + (line + '\n').encode())
                    time.sleep(0.3)
            except OSError as e:
                self.log(f'monitor: {e}')
        threading.Thread(target=run, daemon=True).start()

    def gpio(self, pin, high):
        self.cmd(f'sysbus.gpioPortA OnGPIO {pin} {"true" if high else "false"}')


def make_handler(state, link, monitor):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                body = open(os.path.join(HERE, 'panel.html'), 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == '/events':
                q = queue.Queue(maxsize=256)
                state.listeners.append(q)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                try:
                    with state.lock:
                        snap = json.dumps({'leds': state.leds, 'stats': state.stats})
                    self.wfile.write(f'data: {snap}\n\n'.encode()); self.wfile.flush()
                    last = time.time()
                    while True:
                        try:
                            self.wfile.write(f'data: {q.get(timeout=1.0)}\n\n'.encode())
                        except queue.Empty:
                            pass
                        if time.time() - last > 1.0:
                            last = time.time()
                            link.send('?\n')
                            self.wfile.write(f'data: {json.dumps({"stats": state.stats})}\n\n'.encode())
                        self.wfile.flush()
                except OSError:
                    pass
                finally:
                    state.listeners.remove(q)
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != '/press':
                return self.send_error(404)
            n = int(self.headers.get('Content-Length', 0))
            ev = json.loads(self.rfile.read(n) or b'{}')
            lg, down = int(ev.get('id', -1)), bool(ev.get('down'))
            link.press(lg, down, int(ev.get('pressure', 0x0B00)))
            if lg == SETUP_LOGICAL:
                monitor.gpio(2, down)
            elif lg == SHIFT_LOGICAL:
                monitor.gpio(3, down)
            self.send_response(204)
            self.end_headers()
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--panel', type=int, default=3456, help='M0 front-panel socket (m0 StartPanel <port>)')
    ap.add_argument('--monitor', type=int, default=1234)
    ap.add_argument('--http', type=int, default=8765)
    a = ap.parse_args()
    log = lambda m: print(time.strftime('%H:%M:%S'), m, flush=True)
    state = State()
    link = PanelLink(a.panel, state, log)
    threading.Thread(target=link.run, daemon=True).start()
    srv = ThreadingHTTPServer(('127.0.0.1', a.http), make_handler(state, link, Monitor(a.monitor, log)))
    log(f'front panel on http://localhost:{a.http}')
    srv.serve_forever()


if __name__ == '__main__':
    main()
