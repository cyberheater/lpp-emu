#!/usr/bin/env python3
"""Builds the sequencer user guide: SEQUENCER_MANUAL.pdf (and the intermediate HTML in build/manual/).
usage: python3 scripts/make_manual.py      (needs Google Chrome for the HTML -> PDF step)"""
import html, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'build', 'manual')
PDF = os.path.join(ROOT, 'SEQUENCER_MANUAL.pdf')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

TRACK = ['#ff2020', '#ff8000', '#ffe000', '#40ff40', '#00e0e0', '#2060ff', '#a040ff', '#ff40c0']
WHITE, DIM, OFF = '#ffffff', '#3a3a3a', '#262626'

# ---------------------------------------------------------------- device drawing

TOP = ['Shift', '◀', '▶', 'Session', 'Note', 'Chord', 'Custom', 'Sequencer', 'Projects']
LEFT = {80: '▲', 70: '▼', 60: 'Clear', 50: 'Duplicate', 40: 'Quantise', 30: 'Fixed Length', 20: '▷', 10: '○'}
RIGHT = {89: 'Patterns'}
BOTTOM = ['Record Arm', 'Mute', 'Solo', 'Volume', 'Pan', 'Sends', 'Device', 'Stop Clip']


def positions():
    """index -> (col, row, kind) on a 10 x 11 layout."""
    p = {}
    for c in range(9):
        p[90 + c] = (c, 0, 'btn')
    for y in range(8, 0, -1):
        r = 9 - y
        p[y * 10] = (0, r, 'btn')
        for x in range(1, 9):
            p[y * 10 + x] = (x, r, 'pad')
        p[y * 10 + 9] = (9, r, 'side')
    for x in range(1, 9):
        p[100 + x] = (x, 9, 'track')
        p[x] = (x, 10, 'btn')
    return p


POS = positions()


def device(lit=None, callouts=None, labels=True, width=460, dim_rest=False):
    """SVG of the Launchpad. lit: index -> colour. callouts: [(index, n)] numbered markers."""
    lit = lit or {}
    S, G, M = 34, 6, 22               # cell, gap, margin
    rows_y = lambda r: M + r * (S + G) + (8 if r >= 9 else 0) + (6 if r >= 10 else 0)
    W = M * 2 + 10 * (S + G) - G
    H = rows_y(10) + S * 0.62 + M
    out = [f'<svg viewBox="0 0 {W} {H:.0f}" width="{width}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="Avenir Next, Helvetica Neue, sans-serif">',
           f'<rect x="4" y="4" width="{W-8}" height="{H-8:.0f}" rx="18" fill="#141414"/>']
    for idx, (c, r, kind) in POS.items():
        x, y = M + c * (S + G), rows_y(r)
        col = lit.get(idx, DIM if not dim_rest else '#202020')
        if kind == 'pad':
            out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" rx="5" fill="{col}"/>')
        elif kind == 'track':
            out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S*0.55:.1f}" rx="4" fill="{col}"/>')
        elif kind == 'side':
            out.append(f'<circle cx="{x+S/2}" cy="{y+S/2}" r="{S*0.30:.1f}" fill="{col}"/>')
        else:
            h = S * 0.62 if r == 10 else S
            out.append(f'<rect x="{x+3}" y="{y+3 if r != 10 else y}" width="{S-6}" height="{h-6:.1f}" rx="4" '
                       f'fill="{lit.get(idx, "#303030")}"/>')
        if labels:
            t = None
            if r == 0 and c < 9:
                t = TOP[c]
            elif idx in LEFT:
                t = LEFT[idx]
            elif r == 10:
                t = BOTTOM[c - 1]
            if t:
                fs = 9 if len(t) <= 2 else 5.2
                ty = y + S / 2 + 2 if r != 10 else y + S * 0.31 + 1
                fill = '#111' if idx in lit and lit[idx] not in ('#303030',) else '#bdbdbd'
                words = t.split(' ')
                if len(words) == 2 and len(t) > 7:
                    out.append(f'<text x="{x+S/2}" y="{ty-3}" font-size="{fs}" text-anchor="middle" fill="{fill}">{words[0]}</text>')
                    out.append(f'<text x="{x+S/2}" y="{ty+4}" font-size="{fs}" text-anchor="middle" fill="{fill}">{words[1]}</text>')
                else:
                    out.append(f'<text x="{x+S/2}" y="{ty}" font-size="{fs}" text-anchor="middle" fill="{fill}">{html.escape(t)}</text>')
    for idx, n in callouts or []:
        c, r, kind = POS[idx]
        x, y = M + c * (S + G) + S / 2, rows_y(r) + (S * 0.3 if r >= 9 else S / 2)
        out.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#ffffff" stroke="#111" stroke-width="2"/>'
                   f'<text x="{x}" y="{y+3.6}" font-size="10.5" font-weight="700" text-anchor="middle" fill="#111">{n}</text>')
    out.append('</svg>')
    return ''.join(out)


def step_idx(n):           # step 1-32 -> grid index
    i = n - 1
    return (8 - i // 8) * 10 + i % 8 + 1


def note_idx(p):           # note pad 0-31 -> grid index
    return (1 + p // 8) * 10 + p % 8 + 1


def shade(hexcol, f):
    h = hexcol.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % (int(r * f), int(g * f), int(b * f))


DIGITS = [[0b111, 0b101, 0b101, 0b111], [0b010, 0b110, 0b010, 0b111], [0b111, 0b011, 0b100, 0b111],
          [0b111, 0b011, 0b001, 0b111], [0b101, 0b101, 0b111, 0b001], [0b111, 0b110, 0b001, 0b111],
          [0b100, 0b111, 0b101, 0b111], [0b111, 0b001, 0b010, 0b010], [0b111, 0b111, 0b101, 0b111],
          [0b111, 0b101, 0b111, 0b001]]


def bpm_lit(bpm):
    h, t, u = bpm // 100, bpm // 10 % 10, bpm % 10
    lit = {}
    for row in range(4):
        for col in range(8):
            idx = (1 + (3 - row)) * 10 + col + 1
            on = lambda d, x: DIGITS[d][row] >> (2 - x) & 1
            if col == 0:
                lit[idx] = '#ff8000' if 3 - row < h else '#2a1500'
            elif 1 <= col <= 3 and (h or t) and on(t, col - 1):
                lit[idx] = WHITE
            elif 5 <= col <= 7 and on(u, col - 5):
                lit[idx] = WHITE
            else:
                lit[idx] = '#181818'            # unlit pads are off during the readout
    return lit


# ---------------------------------------------------------------- figures

def fig_overview():
    lit = {}
    red = TRACK[0]
    for s in range(1, 33):
        lit[step_idx(s)] = red if s in (1, 5, 9, 13, 17, 21, 25, 29) else shade(red, 0.18)
    lit[step_idx(7)] = WHITE                                      # playhead
    for p in range(32):
        lit[note_idx(p)] = shade(red, 0.45) if p % 12 in (0, 2, 4, 5, 7, 9, 11) else shade(red, 0.18)
    lit[note_idx(12)] = WHITE
    for t in range(8):
        lit[101 + t] = TRACK[t] if t == 0 else shade(TRACK[t], 0.35)
    lit[20] = '#40ff40'
    lit[97] = WHITE
    lit[98] = '#00c000'
    lit[2] = '#300000'
    lit[3] = '#000830'
    return device(lit, [(84, 1), (34, 2), (101, 3), (2, 4), (20, 5), (10, 6), (89, 7), (98, 8), (90, 9), (80, 10)])


def fig_step_hold():
    lit = {}
    c = TRACK[0]
    for s in range(1, 33):
        lit[step_idx(s)] = shade(c, 0.18)
    for s in (1, 9, 17):
        lit[step_idx(s)] = c
    lit[step_idx(5)] = WHITE                                        # held
    for p in (12, 16, 19):
        lit[note_idx(p)] = c
    for y in range(1, 9):
        lit[y * 10 + 9] = '#ff2020' if y <= 6 else '#303030'
    for g in range(1, 9):
        lit[g] = WHITE if g <= 4 else '#303030'
    return device(lit, [(step_idx(5), 1), (note_idx(16), 2), (69, 3), (3, 4)])


def fig_track_hold():
    lit = {}
    for s in range(1, 17):
        lit[step_idx(s)] = WHITE if s == 3 else '#303050'
    for r in range(8):                       # step rate, slowest left: straight green, triplets purple; 1/8 chosen
        col = '#a040ff' if r in (2, 4, 6) else '#20ff40'
        lit[step_idx(17 + r)] = col if r == 3 else shade(col, 0.45 if r == 5 else 0.2)
    outs = ['#ffffff', '#00ff60', '#00a0ff', '#00ffff']
    for p in range(4):
        lit[note_idx(p)] = outs[p] if p == 2 else shade(outs[p], 0.35)
    for p in range(8, 32):
        lit[note_idx(p)] = '#ffe000' if p == 22 else ('#806000' if p == 20 else '#302800')
    for t in range(8):
        lit[101 + t] = TRACK[t] if t == 2 else shade(TRACK[t], 0.35)
    return device(lit, [(103, 1), (step_idx(3), 2), (note_idx(2), 3), (note_idx(20), 4), (step_idx(20), 5)])


def fig_patterns():
    lit = {}
    for t in range(8):
        for p in range(8):
            idx = (8 - p) * 10 + t + 1
            col = TRACK[t]
            if p == 0:
                lit[idx] = col
            elif t == 1 and p in (1, 2, 3):
                lit[idx] = shade(col, 0.5)
            elif p < (3 if t < 4 else 1):
                lit[idx] = shade(col, 0.2)
            else:
                lit[idx] = '#202020'
    lit[(8 - 2) * 10 + 4] = WHITE                                   # queued
    lit[89] = WHITE
    return device(lit, [(89, 1), (81, 2), (72, 3), (64, 4)])


def fig_tempo():
    lit = bpm_lit(120)
    lit[90] = WHITE
    lit[6] = '#603000'
    lit[20] = '#00c000'
    for s in range(1, 33):
        lit[step_idx(s)] = '#ffa000' if s <= 4 else '#100800'
    return device(lit, [(90, 1), (21, 2), (6, 3), (step_idx(4), 4), (20, 5), (80, 6)])


def fig_projects():
    lit = {98: WHITE}
    for t in range(8):
        lit[101 + t] = WHITE if t == 0 else ('#505050' if t in (1, 2) else '#1c1c1c')
    return device(lit, [(98, 1), (101, 2), (102, 3), (104, 4)])


def fig_record():
    lit = {10: '#ff0000', 20: '#40ff40'}
    for p in range(32):
        lit[note_idx(p)] = shade(TRACK[0], 0.3)
    return device(lit, [(10, 1), (20, 2), (note_idx(12), 3)])


def fig_cover():
    lit = {}
    for t in range(8):
        for s in range(8):
            if (s * 3 + t * 5) % 7 < 3 or s == t:
                lit[(8 - t) * 10 + s + 1] = TRACK[t]
            else:
                lit[(8 - t) * 10 + s + 1] = shade(TRACK[t], 0.14)
        lit[101 + t] = TRACK[t]
    for t in range(8):
        lit[(8 - t) * 10 + 4] = WHITE
    lit[20] = '#40ff40'
    lit[97] = WHITE
    return device(lit, labels=False, width=430)


# ---------------------------------------------------------------- page content

def table(head, rows, cls=''):
    h = ''.join(f'<th>{x}</th>' for x in head)
    b = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def legend(items):
    return '<ol class="legend">' + ''.join(f'<li><b>{a}</b> {b}</li>' for a, b in items) + '</ol>'


def note(text, kind='Tip'):
    cls = 'note warn' if kind == 'Warning' else 'note'
    return f'<div class="{cls}"><span>{kind}</span>{text}</div>'


def figure(svg, caption):
    return f'<figure>{svg}<figcaption>{caption}</figcaption></figure>'


def k(s):
    return f'<span class="key">{s}</span>'


SECTIONS = []


def section(title, body):
    SECTIONS.append((title, body))


section('Introduction', f'''
<p class="lead">The 8-Track Sequencer turns a Launchpad Pro MK3 into a standalone MIDI sequencer. It runs on the
Launchpad itself – no computer is needed once it is installed. Connect synths and drum machines to the two DIN MIDI
outputs (or to a computer over USB) and program up to eight parts at once.</p>
<h3>Key features</h3>
<ul class="features">
<li><b>8 tracks</b>, each with its own MIDI channel, output (USB, DIN 1, DIN 2 or both DIN outs), note range, transpose and step rate (1/32 to a whole bar, including triplets)</li>
<li><b>8 patterns per track</b> (A–H) of up to <b>64 steps</b>, switched and chained independently per track</li>
<li><b>Chords</b> – up to 8 notes on every step</li>
<li>Per-step <b>velocity</b>, <b>gate length</b> and <b>probability</b></li>
<li>Tempo 30–300 BPM with <b>tap tempo</b> and an on-grid <b>BPM readout</b>; <b>swing</b> from 50 % to 75 %</li>
<li><b>Live recording</b> from the pads or an external keyboard, quantised to the nearest step</li>
<li><b>MIDI thru</b>: a keyboard plays whichever track is selected</li>
<li>Sends <b>MIDI clock</b>, or can follow an external clock from USB or DIN In</li>
<li><b>8 project slots</b> saved in the Launchpad’s memory</li>
<li>Playback continues while you use the Launchpad’s Note mode</li>
</ul>
<h3>What you need</h3>
<ul>
<li>A Launchpad Pro MK3 running the sequencer firmware (see <i>Installing the firmware</i> at the end of this guide)</li>
<li>Synths, drum machines or a computer to play, connected to <b>MIDI Out</b>, <b>MIDI Out 2</b> or USB</li>
<li>Optionally, a MIDI keyboard on <b>MIDI In</b> or the USB MIDI port</li>
</ul>
{note("The second DIN socket on the back of the Launchpad is used as <b>MIDI Out 2</b> by this firmware (not as MIDI Thru).", "Note")}
''')

section('Overview', f'''
<p>The sequencer uses the whole surface of the Launchpad. The top half of the grid shows the steps of the selected
track; the bottom half is a keyboard of 32 notes. The coloured row under the grid selects tracks and the row beneath
that holds Mute and Solo.</p>
{figure(fig_overview(), 'The sequencer with track 1 selected and playing')}
{legend([
 ('Step area.', '32 steps of the selected track’s current pattern: steps 1–32, or 33–64 after ▶ (top row = steps 1–8 or 33–40). Lit steps play; brighter = louder. The white pad is the playhead.'),
 ('Note area.', '32 chromatic notes, lowest at the bottom left. Tap a note to hear it and to choose the note new steps get.'),
 ('Track buttons.', 'Tap to select a track, hold for its settings. Each track has its own colour.'),
 ('Mute and Solo.', 'Arm a mode in which the track buttons mute or solo tracks (see <i>Mute and Solo</i>). While a step is held, this whole row sets its gate length.'),
 ('Play.', 'Start / stop. Green = internal clock, orange = following an external clock.'),
 ('Record.', 'Arm live recording.'),
 ('Patterns.', 'Hold to show the pattern map for all eight tracks.'),
 ('Projects.', 'Tap to save, hold to load. Green = saved, amber = unsaved changes.'),
 ('Shift.', 'Hold for tempo, swing, tap tempo and the clock setting.'),
 ('▲ / ▼.', 'Move the note area up or down an octave.'),
])}
<h3>Entering and leaving the sequencer</h3>
<p>Press {k('Sequencer')} to open the sequencer. The first time after power-up, the last project you used is
loaded automatically.</p>
<p>Press {k('Note')} to return to the Launchpad’s Note mode. <b>Playback keeps going</b> while you play in Note mode –
the {k('Sequencer')} button lights green to show it. Press {k('Sequencer')} again to come back.</p>
''')

section('Getting Started', f'''
<p>This walkthrough programs a simple pattern and plays it on a synth connected to <b>MIDI Out</b>.</p>
<ol class="steps">
<li>Connect your synth’s MIDI In to the Launchpad’s <b>MIDI Out</b> socket, and set the synth to receive on
<b>MIDI channel 1</b>.</li>
<li>Press {k('Sequencer')}. Track 1 (red) is selected. New tracks send on <b>MIDI Out</b>, with the MIDI channel
equal to the track number.</li>
<li>Tap a pad in the note area. You hear the note on your synth – it is now the note new steps will use.</li>
<li>Tap steps 1, 5, 9 and 13 in the step area to turn them on.</li>
<li>Press {k('▷')} (Play). The playhead moves across the steps and the synth plays.</li>
<li>Hold step 5 and tap two more note pads: step 5 is now a three-note chord.</li>
<li>Tap track button 2 (orange), choose a note and add some steps. Track 2 plays on MIDI channel 2.</li>
<li>Tap {k('Projects')} to save. The button flashes white, then turns green.</li>
</ol>
{note("Hold <b>Shift</b> at any time to see the current tempo on the grid. Use <b>Shift + ▲ / ▼</b> to change it, or tap <b>Sends</b> in time while holding Shift.")}
''')

section('Programming Steps', f'''
<table class="compact">
<thead><tr><th>Action</th><th>Result</th></tr></thead><tbody>
<tr><td>Tap a note pad</td><td>Choose the note new steps get, and hear it</td></tr>
<tr><td>Tap an unlit step</td><td>Turn it on with the chosen note</td></tr>
<tr><td>Tap a lit step and release</td><td>Turn it off</td></tr>
<tr><td>{k('▲')} / {k('▼')}</td><td>Move the note area up / down an octave</td></tr>
</tbody></table>
<h3>Holding a step</h3>
<p>Hold a step to edit it. While it is held, the note area shows all its notes, the right-hand column shows its
velocity and the bottom row shows its gate length.</p>
{figure(fig_step_hold(), 'Step 5 held: a three-note chord, velocity 96, gate 4/8')}
{legend([
 ('Held step.', 'Shown white while you hold it.'),
 ('Notes.', 'The first note pad you tap sets the step’s note. Tap more pads in the same hold to build a chord of up to 8 notes; tap a lit note again to remove it.'),
 ('Velocity.', 'The right-hand column: top = 127, then 112, 96, 80, 64, 48, 32, bottom = 16.'),
 ('Gate length.', 'The bottom row: 1 (Record Arm) = shortest, 8 (Stop Clip) = the whole step.'),
])}
<p><b>Probability</b>: hold the step and {k('Shift')} – the right-hand column then sets how often the step plays:
top = always (100 %), then 87, 75, 62, 50, 37, 25, bottom = 12 %.</p>
{note("A step you have edited while holding it never turns off when you let go.")}
<div class="keep"><h3>Pages: steps 33–64</h3>
<p>A pattern can have up to 64 steps; the step area shows 32 at a time. {k('◀')} shows steps 1–32, {k('▶')} shows
steps 33–64. The arrow of the page you are on is white; the other arrow is grey when the pattern reaches that page,
dim when it does not, and <b>green while the playhead is on that page</b>. To make a pattern longer than 32 steps, go
to page 2, hold {k('Fixed Length')} and tap the last step. Projects saved before 64 steps load unchanged.</p></div>
<div class="keep"><h3>Copying a step</h3>
<p>Hold {k('Duplicate')} and tap a lit step: it lights <b>cyan</b>. Keep holding {k('Duplicate')} and tap every step
you want a copy on. Each copy gets the same notes (including chords), length, velocity and probability. Press
{k('▶')} / {k('◀')} while still holding {k('Duplicate')} to paste on the other page.</p></div>
<h3>Pattern length and clearing</h3>
{table(['Action', 'Result'], [
 [f'Hold {k("Fixed Length")} + tap a step', 'The pattern ends at that step (1–32, or 33–64 on page 2)'],
 [f'Hold {k("Clear")} + tap a step', 'Clear that step'],
 [f'Hold {k("Clear")} + tap a track button', 'Clear that track’s current pattern (its length stays)'],
], 'compact')}
''')

section('Tracks', f'''
<p>Tap a track button to select it. The step and note areas then show that track, and an external keyboard plays it
(see <i>MIDI Thru</i>). Hold a track button to change the track’s settings.</p>
{figure(fig_track_hold(), 'Track 3 held: MIDI channel 3, output MIDI Out 2, transposed +2, step rate 1/8')}
{legend([
 ('Track button (held).', 'Settings are shown for as long as you hold it.'),
 ('MIDI channel.', 'Steps 1–16 (the top two rows) choose channel 1–16; the current channel is white. ▲ / ▼ also step the channel up and down.'),
 ('Output.', 'Bottom row of the note area, pads 1–4: USB (white), MIDI Out (green), MIDI Out 2 (blue), both DIN outs (cyan).'),
 ('Transpose.', 'Note rows 2–4: −12 … +11 semitones. The dim pad (row 3, pad 5) is 0.'),
 ('Step rate.', 'Steps 17–24 (the third row): how fast the track moves through its steps, slowest on the left. Straight rates are green, triplets purple; the chosen rate is bright.'),
])}
<p>New tracks send on <b>MIDI Out</b> with MIDI channel = track number (track 3 = channel 3).</p>
<div class="keep"><h3>Step rate</h3>
<p>Each track can step at its own speed against the shared tempo, for example a bass line at half speed under a
16th-note hi-hat. Hold the track button and tap a pad in the third row; the slowest rate is on the left:</p>
{table(['Pad', '17', '18', '19', '20', '21', '22', '23', '24'], [
 ['One step =', '1 bar (1/1)', '1/4', '1/4 triplet', '1/8', '1/8 triplet', '1/16 (default)', '1/16 triplet', '1/32'],
 ['Speed', '1/16×', '¼×', '⅜×', '½×', '¾×', '1×', '1.5×', '2×'],
], 'compact')}
<p>All tracks start together when you press Play, so tracks at different rates stay in line. Swing only affects
tracks at 1/16; other rates play straight. Gate lengths scale with the step, and live recording uses the selected
track’s rate. The rate is saved with the project.</p></div>
<div class="keep"><h3>Mute and Solo</h3>
<p>{k('Mute')} and {k('Solo')} in the bottom row arm a mode for the track buttons. The armed button flashes; press it
again to disarm.</p>
{table(['Press', 'Then tap a track button to'], [
 [f'{k("Mute")} (flashes red)', 'Mute or unmute it at once'],
 [f'{k("Solo")} (flashes blue)', 'Solo or unsolo it at once'],
 [f'{k("Shift")} + {k("Mute")} (flashes red and white)', 'Mute or unmute it when its pattern next starts from step 1'],
 [f'{k("Shift")} + {k("Solo")} (flashes blue and white)', 'Solo or unsolo it when its pattern next starts from step 1'],
], 'compact')}
<p>While Mute is armed, the track buttons show unmuted tracks in their colour and muted ones dark red; while Solo is
armed, soloed tracks in their colour and the others dark. A queued change flashes the track button white until it
happens; tap the track again to cancel it. When stopped, a queued change happens at once.</p>
<p>When any track is soloed, only soloed tracks play; a muted track stays silent even if soloed. Outside Mute and
Solo mode, tracks silenced by mute or solo show darker. Mutes and solos are saved with the project.</p></div>
''')

section('Patterns and Chains', f'''
<p>Each track has eight patterns, A–H. Hold {k('Patterns')} to see the pattern map: one <b>column per track</b>
(track 1 on the left) and one <b>row per pattern</b> (A at the top).</p>
{figure(fig_patterns(), 'Pattern map: track 2 chains A–D, track 4 has pattern C queued')}
{legend([
 ('Patterns.', 'Hold to show the map.'),
 ('Current pattern.', 'Lit in the track’s colour.'),
 ('Chained.', 'Medium brightness: part of the track’s chain. Dim = has notes; off = empty.'),
 ('Queued.', 'White: starts when the playing pattern ends.'),
])}
{table(['While holding Patterns', 'Result'], [
 ['Tap a pattern', 'Switch the track to it – at the end of the playing pattern, or at once when stopped'],
 ['Hold a pattern + tap another in the same column', '<b>Chain</b> the range: A–D plays A, B, C, D, A, …'],
 [f'Hold {k("Duplicate")} + tap a pattern', 'Copy the track’s current pattern there'],
 [f'Hold {k("Clear")} + tap a pattern', 'Clear that pattern (its length stays)'],
], 'compact')}
{note("Each track switches and chains on its own, and patterns can have different lengths – use this for polyrhythms.")}
''')

section('Tempo, Swing and Playback', f'''
{figure(fig_tempo(), 'Shift held: 120 BPM on the note area, swing 53 %, Play green (internal clock)')}
{legend([
 ('Shift.', 'Hold to see tempo, swing and the clock setting.'),
 ('BPM readout.', 'An orange bar for the hundreds (1–3 pads), then the tens and units in white.'),
 ('Tap.', 'Shift + Sends (printed <i>Tap</i>) is tap tempo.'),
 ('Swing.', 'The step area shows swing: step 1 = 50 % (straight) … step 26 = 75 %.'),
 ('Play.', 'With Shift: the external clock setting (see <i>MIDI Clock</i>).'),
 ('▲ / ▼.', 'With Shift: tempo.'),
])}
{table(['Action', 'Result'], [
 [f'{k("▷")}', 'Start / stop'],
 [f'{k("Shift")} + {k("▲")} / {k("▼")}', 'Tempo +1 / −1 BPM (30–300)'],
 [f'{k("Shift")} + {k("Fixed Length")} + {k("▲")} / {k("▼")}', 'Tempo +10 / −10 BPM'],
 [f'{k("Shift")} + {k("Sends")} (Tap)', 'Tap tempo: tap in time; the average of the last few taps sets the BPM. A 2-second pause starts over. The button flashes white on each tap.'],
 [f'{k("Shift")} + a step 1–26', 'Swing 50–75 %'],
], 'compact')}
''')

section('Live Recording', f'''
{figure(fig_record(), 'Recording armed and playing')}
{legend([
 ('Record.', 'Tap to arm (dark red); bright red while playing.'),
 ('Play.', 'Recording happens while the sequencer plays.'),
 ('Notes.', 'Play the note pads, or a keyboard on MIDI In or USB.'),
])}
<p>Recorded notes land on the <b>nearest step</b> of the selected track’s current pattern, with their velocity and
their held length as the gate: a note held over several steps plays for as long as you held it. Notes played together are recorded as a <b>chord</b> of up to 8
notes, keeping the loudest velocity.</p>
<p>A note played just ahead of a step is not replayed on that pass – you have already heard it.</p>
<p>Tap {k('○')} again to stop recording.</p>
''')

section('MIDI Thru', f'''
<p>A keyboard connected to <b>MIDI In</b> or to the Launchpad’s USB MIDI port plays the <b>selected track</b>.
Notes, aftertouch, controllers and pitch bend are re-sent on that track’s output and MIDI channel, whatever channel
the keyboard sends on. Select another track and the keyboard plays that track’s instrument.</p>
<p><b>Program changes and bank select are not passed on</b>, so changing presets on the keyboard never changes the
sound of the synth the selected track plays.</p>
<p>A note-off always goes to wherever its note-on went, so changing track while holding keys never leaves notes stuck.</p>
{note("If your keyboard has its own sounds, turn its <b>Local</b> setting off so you only hear the selected track’s instrument.")}
<p>If the keyboard has MIDI Thru switched on, the sequencer’s own notes and controllers come back to it. These echoes
are recognised and dropped, so they do not loop or record twice.</p>
''')

section('MIDI Clock', f'''
<h3>Sending clock</h3>
<p>When the sequencer runs on its own tempo, it sends MIDI clock, start and stop to USB, MIDI Out and MIDI Out 2, so
drum machines and arpeggiators can follow it.</p>
<h3>Internal or external clock</h3>
<p>By default the sequencer runs on its own clock and ignores any clock, start or stop arriving on <b>MIDI In</b> or
the USB MIDI port; {k('▷')} is <b>green</b>. Press {k('Shift')} + {k('▷')} to switch to following an external clock
and back. While {k('Shift')} is held, {k('▷')} shows the setting:</p>
{table(['▷ with Shift held', 'Setting'], [
 ['<span class="swatch" style="background:#00c000"></span> Green', 'Internal clock (default): ignore incoming clock, start and stop; run on and send the sequencer’s own clock'],
 ['<span class="swatch" style="background:#ff6000"></span> Orange', 'Follow an external clock'],
], 'compact')}
<h3>Following an external clock</h3>
<ul>
<li>{k('▷')} flashes <b>orange</b>.</li>
<li>The clock is passed on to both DIN outputs.</li>
<li>Tempo controls and tap tempo have no effect.</li>
<li>Half a second after the last clock pulse, the sequencer carries on with its own clock.</li>
</ul>
<p>The setting is saved with the project; projects saved before it existed load on the internal clock.</p>
{note("Some synths (a Korg minilogue, for example) send a clock that stutters while they load presets. Only follow an external clock when you need to.")}
{note("A synth with MIDI Thru switched on sends the sequencer’s clock straight back. The sequencer recognises its own clock and ignores it, so the tempo cannot run away.", "Note")}
''')

section('Projects', f'''
{figure(fig_projects(), 'Projects held: slot 1 current, slots 2 and 3 saved')}
{legend([
 ('Projects.', 'Tap to save to the current slot (flashes white). Hold to choose a slot.'),
 ('Current slot.', 'White.'),
 ('Saved slot.', 'Dim. Tap to load it.'),
 ('Empty slot.', 'Off. Tap to make it the slot the next save goes to.'),
])}
<p>The {k('Projects')} button is <b>green</b> when everything is saved and <b>amber</b> when there are unsaved
changes.</p>
<p>A project stores all tracks, patterns and chains, channels, outputs, transpose, step rates, tempo, swing and the external
clock setting. The last used slot is loaded automatically after power-up.</p>
''')

section('Quick Reference', table(['Control', 'Tap', 'With Shift', 'Hold + …'], [
 ['Step pad', 'Toggle step', 'Set swing (steps 1–26)', 'Note pads = notes / chord; right column = velocity (+ Shift = probability); bottom row = gate'],
 ['Note pad', 'Choose and hear note', '–', '–'],
 ['Track button', 'Select track', '–', 'Steps 1–16 = channel; steps 17–24 = step rate; note row 1 = output; rows 2–4 = transpose; ▲ / ▼ = channel'],
 ['Mute / Solo', 'Arm: track buttons mute / solo at once', 'Arm: changes wait for the pattern start', '–'],
 ['Sends', '–', 'Tap tempo', '–'],
 ['▲ / ▼', 'Octave', 'Tempo ±1 (±10 with Fixed Length)', '–'],
 ['▷ Play', 'Start / stop', 'Internal (green) / external clock (orange)', '–'],
 ['○ Record', 'Arm / disarm recording', '–', '–'],
 ['Fixed Length', '–', '–', '+ step = pattern length'],
 ['◀ / ▶', 'Steps 1–32 / 33–64', '–', '–'],
 ['Clear', '–', '–', '+ step = clear step; + track = clear pattern'],
 ['Duplicate', '–', '–', '+ step = copy it, then + steps = paste; with Patterns: copy pattern'],
 ['Patterns', '–', '–', 'Pattern map: switch, chain, copy, clear'],
 ['Projects', 'Save', '–', 'Track row = choose / load slot'],
 ['Note', 'Note mode (playback continues)', '–', '–'],
], 'ref'))

section('Installing the Firmware', f'''
<p>The sequencer is part of a custom build of the open-source CoreFW firmware
(github.com/anthonyhfm/launchpad-core-firmware, GPL-3.0). No Novation firmware is supplied with it.</p>
{note("This firmware is an early beta, tested on very few devices. Flashing your own Launchpad is at your own risk: the firmware may misbehave or lose your projects and settings, and an interrupted or failed update can leave the Launchpad needing recovery from the bootloader. The authors accept no responsibility for damage to your device or data. It is not Novation software and Novation does not support it.", "Warning")}
<h3>Installing</h3>
<ol class="steps">
<li>Download the latest <code>.syx</code> file from github.com/cyberheater/Launchpad-Pro-MK3-Custom-firmware/releases, or build it
yourself: <code>cargo lppmk3</code> in that repository (branch <code>lppmk3-sequencer</code>) makes
<code>build/lppmk3/fw.syx</code>.</li>
<li>Unplug the Launchpad. Hold <b>Setup</b> while plugging the USB cable back in. The Launchpad starts in bootloader
mode and a MIDI port with "Bootloader" in its name appears.</li>
<li>Send the <code>.syx</code> file to that port. Use CoreFW's <code>python3 tools/flash.py &lt;file&gt;.syx</code>
(needs <code>pip install mido python-rtmidi</code>), the Mac-only <code>swift scripts/flash_syx.swift &lt;file&gt;.syx</code>
from github.com/cyberheater/lpp-emu, or any SysEx tool (SysEx Librarian, MIDI-OX). Do not unplug the Launchpad while
it is sending.</li>
<li>The Launchpad restarts with the sequencer firmware. Press <b>Sequencer</b> to open it.</li>
</ol>
<h3>Returning to the original firmware</h3>
<p>Enter bootloader mode the same way and update the Launchpad with Novation Components.</p>
{note("Projects are stored separately from the firmware, so updating the sequencer firmware should keep them. Projects saved by earlier sequencer versions load in later ones.", "Note")}
''')

# ---------------------------------------------------------------- document

CSS = '''
@page { size: A4; margin: 20mm 18mm 18mm 18mm;
  @top-left { content: "8-Track Sequencer for Launchpad Pro MK3 — User Guide"; font: 8pt "Avenir Next", sans-serif; color: #888; }
  @bottom-right { content: counter(page); font: 600 9pt "Avenir Next", sans-serif; color: #444; } }
@page :first { margin: 0; @top-left { content: none } @bottom-right { content: none } }
* { box-sizing: border-box; }
body { font-family: "Avenir Next", "Helvetica Neue", sans-serif; font-size: 10pt; line-height: 1.5; color: #1a1a1a; margin: 0; }
.cover { width: 210mm; height: 297mm; background: #0d0d0d; color: #fff; padding: 26mm 22mm; position: relative; page-break-after: always; overflow: hidden; }
.cover .eyebrow { font-size: 11pt; letter-spacing: .25em; text-transform: uppercase; color: #9a9a9a; }
.cover h1 { font-size: 44pt; font-weight: 300; line-height: 1.05; margin: 8mm 0 4mm; letter-spacing: -.01em; }
.cover h2 { font-size: 16pt; font-weight: 400; color: #cfcfcf; margin: 0; }
.cover .stripe { display: flex; gap: 3mm; margin: 12mm 0 14mm; }
.cover .stripe i { flex: 1; height: 3mm; border-radius: 2mm; }
.cover .art { text-align: center; }
.cover .foot { position: absolute; left: 22mm; right: 22mm; bottom: 18mm; font-size: 7.5pt; color: #8a8a8a; line-height: 1.5; }
.toc { page-break-after: always; }
.toc h1, section h1 { font-size: 26pt; font-weight: 300; margin: 0 0 6mm; letter-spacing: -.01em; }
.toc ol { list-style: none; padding: 0; margin: 0; counter-reset: t; }
.toc li { counter-increment: t; display: flex; align-items: baseline; padding: 2.4mm 0; border-bottom: 1px solid #e3e3e3; font-size: 12pt; }
.toc li::before { content: counter(t); width: 12mm; font-weight: 600; color: #ff2020; }
section { page-break-before: always; }
section .num { font-size: 10pt; font-weight: 600; letter-spacing: .2em; color: #888; text-transform: uppercase; }
section h1 { border-bottom: 2px solid #111; padding-bottom: 3mm; }
h3 { font-size: 12.5pt; font-weight: 600; margin: 6mm 0 2mm; }
p { margin: 0 0 3mm; }
p.lead { font-size: 12pt; line-height: 1.55; color: #333; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
ul.features li { margin-bottom: 1.2mm; }
ol.steps { counter-reset: s; list-style: none; padding: 0; }
ol.steps li { counter-increment: s; position: relative; padding: 0 0 2.6mm 10mm; }
ol.steps li::before { content: counter(s); position: absolute; left: 0; top: -.3mm; width: 6.4mm; height: 6.4mm; border-radius: 50%; background: #111; color: #fff; font-size: 8.5pt; font-weight: 600; text-align: center; line-height: 6.4mm; }
figure { margin: 4mm 0 3mm; text-align: center; page-break-inside: avoid; }
figure svg { max-width: 100%; height: auto; }
figcaption { font-size: 8.5pt; color: #777; margin-top: 1.5mm; font-style: italic; }
ol.legend { list-style: none; padding: 0; counter-reset: l; columns: 2; column-gap: 8mm; font-size: 9pt; margin-bottom: 4mm; }
ol.legend li { counter-increment: l; position: relative; padding-left: 8mm; margin-bottom: 2mm; break-inside: avoid; }
ol.legend li::before { content: counter(l); position: absolute; left: 0; top: 0; width: 5.2mm; height: 5.2mm; border-radius: 50%; border: 1.5px solid #111; font-size: 7.5pt; font-weight: 700; text-align: center; line-height: 4.9mm; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9pt; page-break-inside: avoid; }
th { text-align: left; font-weight: 600; background: #111; color: #fff; padding: 2mm 3mm; }
td { padding: 2mm 3mm; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
tr:nth-child(even) td { background: #f6f6f6; }
table.ref td:first-child { font-weight: 600; white-space: nowrap; }
.key { display: inline-block; border: 1px solid #999; border-radius: 1.2mm; padding: 0 1.4mm; font-size: 8.5pt; font-weight: 600; line-height: 1.45; background: #f3f3f3; white-space: nowrap; }
th .key { color: #111; }
.note { border-left: 3px solid #ff8000; background: #fff6ec; padding: 2.6mm 4mm; margin: 3mm 0 4mm; font-size: 9.2pt; page-break-inside: avoid; }
.note span { display: block; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; font-size: 7.5pt; color: #c05800; margin-bottom: .6mm; }
.keep { break-inside: avoid; page-break-inside: avoid; }
.note.warn { border-left-color: #d01818; background: #fdeeee; }
.note.warn span { color: #b01010; }
.swatch { display: inline-block; width: 3.4mm; height: 3.4mm; border-radius: .8mm; vertical-align: -.5mm; margin-right: 1mm; }
code { font-family: Menlo, monospace; font-size: 8.3pt; background: #f1f1f1; padding: 0 1mm; border-radius: 1mm; }
'''


def build():
    stripe = ''.join(f'<i style="background:{c}"></i>' for c in TRACK)
    cover = f'''<div class="cover">
<div class="eyebrow">User Guide</div>
<h1>8-Track<br>Sequencer</h1>
<h2>Standalone firmware for Launchpad Pro MK3</h2>
<div class="stripe">{stripe}</div>
<div class="art">{fig_cover()}</div>
<div class="foot"><b style="color:#ff8a3d">Early beta – flash at your own risk.</b> Community firmware based on CoreFW (GPL-3.0). Not made, endorsed or supported by Novation or Focusrite.
Launchpad and Launchpad Pro are trademarks of Focusrite Audio Engineering Ltd, used here only to identify the hardware.</div>
</div>'''
    toc = '<div class="toc"><h1>Contents</h1><ol>' + ''.join(f'<li>{t}</li>' for t, _ in SECTIONS) + '</ol></div>'
    body = ''.join(f'<section><div class="num">Section {i}</div><h1>{t}</h1>{b}</section>'
                   for i, (t, b) in enumerate(SECTIONS, 1))
    doc = f'<!doctype html><html><head><meta charset="utf-8"><title>8-Track Sequencer User Guide</title>' \
          f'<style>{CSS}</style></head><body>{cover}{toc}{body}</body></html>'
    os.makedirs(OUT_DIR, exist_ok=True)
    src = os.path.join(OUT_DIR, 'manual.html')
    with open(src, 'w') as f:
        f.write(doc)
    subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-pdf-header-footer', f'--print-to-pdf={PDF}',
                    'file://' + src], check=True, stderr=subprocess.DEVNULL)
    print('wrote', PDF)


if __name__ == '__main__':
    build()
