#!/usr/bin/env python3
"""Old-format conversion test. Run with Renode (run.resc) up.
  migtest.py old  (old 8-project firmware, fresh flash) project 1: steps 1/5 = D4 and per-track pattern B step 2;
                  save. Project 2 (empty, becomes the save target): + step 7, save. Project 6 (high area): + step 8,
                  save. Then load project 2 again so it is the last used one.
  migtest.py new  (new firmware, same flash) the conversion runs on entry: project 2 is open; projects 1, 2 and 6
                  are there with their steps; pattern 2 holds project 1's old pattern B."""
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
def top16_xy(n): return (8 - n // 8) * 10 + n % 8 + 1
def lit(lg): return sum(leds.get(lg, (0, 0, 0))) > 150   # beat markers (steps 1, 5, ...) glow at ~72
def steps(): return [n for n in range(1, 9) if lit(step_xy(n))]
def save(): press(98); time.sleep(1.5)

time.sleep(1.0)
press(97); time.sleep(1.5)
if sys.argv[1] == 'old':
    press(note_xy(14)); press(step_xy(1)); press(step_xy(5))
    down(89); press(71); up(89)                      # track 1 -> pattern B (old layout: row 7, column 1)
    press(step_xy(2))
    down(89); press(81); up(89)                      # back to pattern A
    save()
    down(98); press(102); up(98); time.sleep(0.5)    # project 2: empty -> save target
    press(step_xy(7)); save()
    down(98); press(106); up(98); time.sleep(0.5)    # project 6
    press(step_xy(8)); save()
    down(98); press(102); up(98); time.sleep(1.0)    # load project 2 (last used)
    print('old firmware, project 2 steps:', steps(), '(expect [1, 5, 7])')
else:
    print('converted, open project steps:', steps(), '(expect [1, 5, 7] - project 2)')
    down(98); time.sleep(0.4)
    print('projects 1-8 while held:', [leds.get(top16_xy(n)) for n in range(8)], '(2 white; 1, 6 dim)')
    up(98); time.sleep(0.6)
    for n, want in ((1, [1, 5]), (6, [1, 5, 7, 8])):
        down(98); press(top16_xy(n - 1)); up(98); time.sleep(1.2)
        print(f'project {n} steps:', steps(), f'(expect {want})')
    down(89); time.sleep(0.4)
    print('pattern 2 light (has notes = dim orange):', leds.get(top16_xy(1)), ' pattern 3:', leds.get(top16_xy(2)))
    press(top16_xy(1)); up(89); time.sleep(0.5)
    print('pattern 2 steps:', steps(), '(expect [2])')
