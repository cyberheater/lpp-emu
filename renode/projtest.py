#!/usr/bin/env python3
"""Project switching test (16 projects, top two grid rows while Projects is held). Run with Renode (run.resc) up.
  projtest.py program  project 1: steps 1/5 = D4; switch to project 10 (saves project 1, opens a blank one); step 3 =
                       E4; switch back to project 1 and check it came back; then switch to project 10 and stay there.
  projtest.py verify   (after a restart) project 10 is open with step 3 lit; project 1 still holds steps 1/5."""
import os, socket, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'm0'))
from panel_bridge import LOGICAL_TO_CONTROL, HW_LED_TO_LOGICAL  # noqa: E402

panel = socket.create_connection(('127.0.0.1', 3456))
leds = {}
lock = threading.Lock()

def reader(sock):
    buf = b''
    while True:
        d = sock.recv(65536)
        if not d:
            return
        buf += d
        *lines, buf = buf.split(b'\n')
        with lock:
            for ln in lines:
                f = ln.decode().split()
                if len(f) == 5 and f[0] == 'l' and HW_LED_TO_LOGICAL.get(int(f[1])) is not None:
                    leds[HW_LED_TO_LOGICAL[int(f[1])]] = tuple(map(int, f[2:]))

threading.Thread(target=reader, args=(panel,), daemon=True).start()
def down(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 2800\n'.encode()); time.sleep(0.1)
def up(lg): panel.sendall(f'p {LOGICAL_TO_CONTROL[lg]} 0\n'.encode()); time.sleep(0.1)
def press(lg): down(lg); up(lg)
def step_xy(n): i = n - 1; return (8 - i // 8) * 10 + i % 8 + 1
def note_xy(pad): return (1 + pad // 8) * 10 + pad % 8 + 1
def top16_xy(n): return (8 - n // 8) * 10 + n % 8 + 1      # n: 0 = project / pattern 1
def lit(lg): return sum(leds.get(lg, (0, 0, 0))) > 150   # beat markers (steps 1, 5, ...) glow at ~72
def steps(): return [n for n in range(1, 9) if lit(step_xy(n))]
def projects():
    down(98); time.sleep(0.4)
    v = {n + 1: leds.get(top16_xy(n)) for n in (0, 1, 9)}
    up(98); time.sleep(0.6)
    return v
def switch(n):
    down(98); press(top16_xy(n - 1)); up(98); time.sleep(1.0)

time.sleep(1.0)
press(97); time.sleep(0.8)
if sys.argv[1] == 'program':
    press(note_xy(14)); press(step_xy(1)); press(step_xy(5)); time.sleep(0.3)
    print('project 1 steps lit:', steps(), '(expect [1, 5])')
    switch(10)
    print('project 10 steps lit:', steps(), '(expect [] - new project)')
    press(note_xy(16)); press(step_xy(3)); time.sleep(0.3)
    switch(1)
    print('back on project 1, steps lit:', steps(), '(expect [1, 5])')
    print('projects 1, 2, 10 while held:', projects(), '(1 white, 2 dark, 10 dim)')
    switch(10)
    print('project 10 again, steps lit:', steps(), '(expect [3])')
else:
    print('after restart, steps lit:', steps(), '(expect [3] - project 10 is current)')
    print('projects 1, 2, 10 while held:', projects(), '(1 dim, 2 dark, 10 white)')
    switch(1)
    print('project 1 steps lit:', steps(), '(expect [1, 5])')
