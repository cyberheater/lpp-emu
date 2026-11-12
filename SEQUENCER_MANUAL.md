# Launchpad Pro MK3 Sequencer — User Manual

An 8-track step sequencer that runs on the Launchpad Pro MK3 itself, with no computer. Each track plays its own
part on its own MIDI channel, sent to USB, DIN Out 1, DIN Out 2 or both DIN outs.

| | |
|---|---|
| Tracks | 8, each with its own MIDI channel, output, octave range, transpose and step rate |
| Patterns | 16 per project, shared by all 8 tracks, can be chained |
| Steps | up to 64 per pattern, shown 32 at a time |
| Notes per step | up to 8 (chords) |
| Per step | velocity, gate length, probability |
| Global | tempo 30–300 BPM, swing 50–75 %, external MIDI clock sync |
| Projects | 32 in the Launchpad's flash (only the steps in use are stored) |

The sequencer is part of a custom build of [CoreFW](https://github.com/anthonyhfm/launchpad-core-firmware) (GPL-3.0).
See *Installing* at the end.

---

## 1. The layout

Button names below are the ones printed on the Launchpad.

```
               Shift  ◀  ▶  Session  Note  Chord  Custom  Sequencer  Projects
              ┌────────────────────────────────────┐
  ▲           │ steps 1 – 8                        │ Patterns
  ▼           │ steps 9 – 16        STEP AREA      │
  Clear       │ steps 17 – 24   (selected track's  │   right column:
  Duplicate   │ steps 25 – 32    current pattern)  │   velocity /
              ├────────────────────────────────────┤   probability bar
  Quantise    │ notes 25 – 32                      │   while a step
  Fixed Length│ notes 17 – 24       NOTE AREA      │   is held
  ▷ Play      │ notes 9 – 16   (32 chromatic notes)│
  ○ Record    │ notes 1 – 8    (lowest)            │
              └────────────────────────────────────┘
               [1] [2] [3] [4] [5] [6] [7] [8]        track select (coloured)
               Record Arm, Mute, Solo, Volume,        Mute / Solo modes
               Pan, Sends, Device, Stop Clip
```

- **Step area** (top four rows): 32 steps of the selected track's current pattern, steps 1–32 or 33–64 (see
  *Pages*). Lit = the step plays,
  brighter = louder. The playhead is shown as it moves.
- **Note area** (bottom four rows): 32 chromatic notes, lowest bottom-left. Tap one to hear it and to choose the
  note that new steps get.
- **Track select row**: the coloured buttons directly under the grid. Tap to select a track; hold for its settings.
- **Bottom row**: **Mute** and **Solo** arm a mode in which the track buttons mute or solo tracks (see
  *Mute and Solo*). While a step is held, the whole row sets its gate length.

### Opening and leaving the sequencer

- **Sequencer** opens it. The first time after power-up, the current project is opened.
- **Note** goes back to the normal note mode. **Playback keeps going** in the background; the Sequencer button
  shows green while it plays. Press Sequencer again to return.

---

## 2. Programming steps

| Action | Result |
|---|---|
| Tap a note pad | Choose the note new steps get (and hear it on the track's output) |
| Tap an unlit step | Turn it on, with the chosen note |
| Tap a lit step (and release without editing) | Turn it off |
| ▲ / ▼ | Move the note area up / down an octave |

### Editing a step: hold it

While you hold a step pad:

- **Note pads** — the first pad you tap sets the step's note. Tap more pads in the same hold to build a **chord**
  (up to 8 notes); tap a lit note again to remove it. The note area shows every note in the held step.
- **Right-hand column** — **velocity**: top = 127, then 112, 96, 80, 64, 48, 32, bottom = 16.
- **Bottom row** (Record Arm … Stop Clip) — **gate length** in eighths of a step: 1 = shortest, 8 = the whole step.
- **Shift + right-hand column** — **probability**: top = always (100 %), then 87, 75, 62, 50, 37, 25, bottom = 12 %.

Editing a step while holding it never turns it off on release.

### Probability page

Tap **Probability** (right-hand column, 5th button down) to see the chance of 8 steps at once. The button lights
cyan and the whole grid shows the selected track's steps as **bars**, one column per step:

- Each bar is filled from the bottom up to the step's probability: top row = always (100 %), then 87, 75, 62, 50, 37,
  25, bottom row = 12 %. A full column always plays.
- **Tap a pad** in a column to set that step's probability (the row you tap becomes the top of its bar).
- Steps that are off show faint and can't be set; steps past the end of the pattern are dark. The playing step's
  bar lights white.
- **◀ / ▶** move 8 steps at a time (steps 1–8, 9–16 … up to 57–64); an arrow is lit when there are more steps that
  way. The page opens on the first 8 steps of the page you were looking at.

Tap **Probability** again to go back to the steps. Track buttons still select tracks while the page is open.

### Mutate

**Mutation** (right-hand column, 6th button down) rearranges the **selected track's** part of the current pattern
for instant variations:

- **Tap** — shuffle: about a quarter of the lit steps (at least one) either **move** to another step (swapping places
  with whatever is there) or **swap notes** with another lit step. The part keeps the same hits and notes in a new
  arrangement. Tap again to shuffle further. The button turns **purple** while the part is mutated.
- **Long press** (hold for about half a second) — **back to the original**: the part returns exactly to how it was
  before the first tap, and the button flashes white.

The original is remembered per track until you restore it, switch project, or turn the Launchpad off. If you mutate a
different pattern on the same track, that pattern's original is remembered instead (the first one stays as it is
now). Edits you make while a part is mutated are lost when you restore it. Saving stores the part as it currently is.

### Pages: steps 33–64

A pattern can have up to 64 steps; the step area shows 32 at a time.

| Button | Shows |
|---|---|
| **◀** | Page 1: steps 1–32 |
| **▶** | Page 2: steps 33–64 |

The arrow of the page you are on is white. The other arrow is grey when the pattern reaches that page, dim when it
does not, and **green while the playhead is on that page**. To make a pattern longer than 32 steps, go to page 2, hold
**Fixed Length** and tap the last step. Projects saved before 64 steps load unchanged.

### Copying a step

Hold **Duplicate** and tap a lit step: it lights **cyan**. Keep holding Duplicate and tap every step you want a copy
on. Each copy gets the same notes (including chords), length, velocity and probability. Press ▶ / ◀ while still
holding Duplicate to paste on the other page. Let go of Duplicate when you are done.

### Pattern length and clearing

| Action | Result |
|---|---|
| Hold **Fixed Length** + tap a step | The pattern ends at that step (1–32, or 33–64 on page 2) |
| Hold **Clear** + tap a step | Clear that step |
| Hold **Clear** + tap a track button | Clear that track's current pattern (its length stays) |

---

## 3. Tracks

Tap a **track button** to select it: the step area and note area then show that track, and a keyboard plays it
(see *MIDI thru*).

Hold a **track button** to change its settings:

| While holding a track button | Sets |
|---|---|
| Steps 1–16 (top two rows) | **MIDI channel** 1–16 |
| ▲ / ▼ | MIDI channel +1 / −1 |
| Note area, bottom row, pads 1–4 | **Output**: 1 USB (white), 2 DIN 1 (green), 3 DIN 2 (blue), 4 DIN 1 + 2 (cyan) |
| Note area, rows 2–4 | **Transpose** −12 … +11 semitones; the dim pad (row 3, pad 5) is 0 |
| Steps 17–24 (third row) | **Step rate** (below) |

New tracks start on **DIN 1**, with MIDI channel = track number (track 3 = channel 3).

### Step rate

Each track can step at its own speed against the shared tempo (e.g. a bass line at half speed under 16th hi-hats).
Hold the track button and tap a pad in the third row of steps, slowest on the left (straight rates green, triplets
purple, chosen = bright):

| Pad | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|
| One step = | 1 bar (1/1) | 1/4 | 1/4 triplet | 1/8 | 1/8 triplet | **1/16 (default)** | 1/16 triplet | 1/32 |
| Speed | 1/16× | ¼× | ⅜× | ½× | ¾× | 1× | 1.5× | 2× |

All tracks start together on Play, so they stay in line. Swing only affects tracks at 1/16; other rates play
straight. Gate lengths scale with the step; live recording uses the selected track's rate. Saved with the project.

### Mute and Solo

**Mute** and **Solo** in the bottom row arm a mode for the track buttons. The armed button flashes; press it again to
disarm.

| Press | Then tap a track button to |
|---|---|
| **Mute** (flashes red) | Mute or unmute it at once |
| **Solo** (flashes blue) | Solo or unsolo it at once |
| **Shift + Mute** (flashes red and white) | Mute or unmute it when its pattern next starts from step 1 |
| **Shift + Solo** (flashes blue and white) | Solo or unsolo it when its pattern next starts from step 1 |

While Mute is armed, the track buttons show unmuted tracks in their colour and muted ones dark red; while Solo is
armed, soloed tracks in their colour and the others dark. A queued change flashes the track button white until it
happens; tap the track again to cancel it. When stopped, a queued change happens at once.

When any track is soloed, only soloed tracks play; a muted track stays silent even if soloed. Outside Mute and Solo
mode, tracks silenced by mute or solo show darker. Mutes and solos are saved with the project.

---

## 4. Patterns and chaining

A project has 16 patterns. A pattern holds **all 8 tracks**, and every track is always on the same pattern: switching
pattern switches the whole song. Tap **Patterns** (top of the right-hand column) to open the pattern view: the
button lights white, the top two grid rows show the 16 patterns (1–8 on the top row, 9–16 on the row below) and the
rest of the grid stays dark. The view **stays open** until you tap Patterns again, so you can pick and chain patterns
with both hands free. You can also hold Patterns, tap a pattern and let go: the view then closes by itself.

| Colour | Meaning |
|---|---|
| White | the current pattern |
| Orange | part of the chain |
| Dim orange | has notes |
| Cyan | queued (starts at the end of the playing pattern) |

| In the pattern view | Result |
|---|---|
| Tap a pattern | Switch to it — at the end of the playing pattern, or at once when stopped |
| Hold one pattern + tap another | **Chain** the range (e.g. 1–4 plays 1, 2, 3, 4, 1, …) |
| Hold **Duplicate** + tap a pattern | Copy the current pattern (all tracks) there |
| Hold **Clear** + tap a pattern | Clear that pattern on all tracks (its length stays) |

Each track's part of a pattern keeps its own length, so tracks can still run polymetric lengths.

---

## 5. Playing, tempo and swing

| Action | Result |
|---|---|
| **Play** (▷) | Start / stop |
| **Shift + ▲ / ▼** | Tempo +1 / −1 BPM |
| **Shift + Fixed Length + ▲ / ▼** | Tempo +10 / −10 BPM |
| **Shift + Sends** (printed *Tap*) | Tap tempo — tap in time; the average of the last few taps sets the BPM. A 2-second pause starts over |
| Hold **Shift**, tap a step 1–26 | **Swing**: step 1 = 50 % (straight) … step 26 = 75 % |

**Tempo readout**: while Shift is held, the note area shows the BPM — an orange bar on the left for the hundreds
(1–3 pads), then the tens and units digits in white. The Sends/Tap button flashes white on each tap.

**Play button colours**: green = playing on the internal clock (the default), orange = following an external clock.

---

## 6. Live recording

1. Tap **Record Arm** (first button of the bottom row) or **○** (bottom of the left column) to arm recording. Both
   light dark red.
2. Press **Play** (with the count-in on, the grid first flashes red 4 times). While playing, both are bright red.
3. Play notes on the note pads, or on a keyboard connected to the USB MIDI port or DIN In.

Notes land on the **nearest step** of the selected track's current pattern, with their velocity and their held
length as the gate: a note held over several steps plays for as long as you held it. Notes played together are recorded as a **chord** (up to 8; the loudest
velocity is kept). A note you play just ahead of a step is not replayed on that pass — you already heard it.

Tap Record again to disarm.

### Count-in

With Record armed, pressing **Play** first counts **one bar in**: the whole grid flashes **red 4 times**, one flash per
beat at the current tempo, and recording starts on the next downbeat. Notes played during the count-in are not
recorded. Press Play again during the count-in to cancel it.

The count-in is **on** by default. To switch it off (or on again), open the **Setup** page and tap the **first pad of
the second row from the bottom**: bright red = on, dim = off. It is remembered when you leave Setup. There is no
count-in while the sequencer follows an external clock (the external Start decides when it begins).

### Step recording (while stopped)

Arm **Record** while the sequencer is **stopped** to enter notes one step at a time:

1. Tap **Record** (dark red). A **white cursor** appears on step 1.
2. Play a note on the note pads or a keyboard. It goes on the cursor step, with its velocity, and the cursor moves
   to the next step when you let go.
3. Keep playing: each note fills the next step. To record a **chord**, hold the notes together; the cursor moves on
   once you have released them all.
4. To leave a **rest** (or go back and redo a step), tap the step you want next: the cursor jumps there, and the
   steps in between keep whatever they had.
5. After the pattern's **last step**, Record disarms by itself and the cursor returns to step 1.

Recorded steps get the default gate (half a step); set it afterwards by holding the step. The cursor follows onto
page 2 for steps 33–64. While Record is armed and stopped, tapping a step only moves the cursor; disarm Record to
switch steps on and off again. Press **Play** at any time to hear the result (Record stays armed, so playing then
records live).

---

## 7. MIDI thru (playing from a keyboard)

A keyboard on the **USB MIDI port** or **DIN In** plays the **selected track**: notes, aftertouch, controllers and
pitch bend are re-sent on that track's output and MIDI channel, whatever channel the keyboard sends on. Select
another track and the keyboard plays that one instead.

**Program changes and bank select are not passed on**, so changing presets on the keyboard never changes the sound
of the synth the selected track plays.

If your keyboard has its own sound, turn its **Local** setting off so you only hear the sound of the selected
track. Echoes from a keyboard with MIDI Thru switched on are recognised and dropped, so they do not loop or
double-record.

---

## 8. MIDI clock

**Sending**: when playing on its own clock, the sequencer sends MIDI clock, start and stop to USB and both DIN outs.

**Internal clock (default)**: the sequencer runs on its own tempo and ignores any clock, start or stop arriving on
the USB MIDI port or DIN In. Play is **green**.

**Shift + Play** switches between the internal clock and following an external clock. While Shift is held, Play
shows the setting:

| Play (Shift held) | Setting |
|---|---|
| Green | Internal clock (default): ignore incoming clock, start and stop; run on and send the sequencer's own clock |
| Orange | Follow an external clock |

**Following an external clock**: clock, start, continue and stop arriving on the USB MIDI port or DIN In drive the
sequencer. Play flashes **orange**, the external clock is passed on to both DIN outs, and tempo and tap tempo have no
effect. 500 ms after the last clock pulse the sequencer carries on with its own clock.

The setting is saved with the project; projects saved before this setting existed load on the internal clock.
Some synths (a Korg minilogue, for example) send a clock that stutters while they load presets, so only follow an
external clock when you need to.

The sequencer also ignores its own clock coming back (a synth with MIDI Thru on DIN In), so the clock cannot run
away.

---

## 9. Projects (saving and switching)

| Action | Result |
|---|---|
| Tap **Projects** | Save the current project (the button flashes white) |
| Hold **Projects** | The top four grid rows show the 32 projects (1–8 on the top row): white = current, dim = saved, dark = empty |
| Hold **Projects** + tap a project | Switch to it. The current project is saved first; an empty one opens as a new, blank project |

The **Projects** button is **green** when everything is saved and **amber** when there are unsaved changes.

A project holds everything: all tracks, 16 patterns, chains, channels, outputs, transpose, step rates, tempo, swing and
the external-clock setting. The current project opens automatically at power-up.

Only the steps in use are stored, so a project normally takes a few KB. Each project has room for about 2,500 used
steps (of the 8 × 16 × 64 possible) — every track playing a full 16-step part in all 16 patterns is 2,048. A project
fuller than that cannot be saved.

---

## 10. Quick reference

| Control | Alone | With Shift | Held + … |
|---|---|---|---|
| Step pad | toggle step | set swing | note pads = notes/chord, right column = velocity (+Shift = probability), bottom row = gate |
| Note pad | choose / preview note | — | — |
| Track button | select track | — | steps 1–16 = channel, steps 17–24 = step rate, note row 1 = output, rows 2–4 = transpose |
| Mute / Solo | arm: track buttons mute / solo at once | arm: changes wait for the pattern start | — |
| Sends | — | tap tempo | — |
| ▲ / ▼ | octave | tempo ±1 (±10 with Fixed Length) | (track held) channel ±1 |
| Play | start / stop (Record armed: 1 bar red count-in first) | internal clock (green) / follow external (orange) | — |
| Record (○) / Record Arm (bottom row 1) | arm recording (stopped = step recording) | — | — |
| Fixed Length | — | — | + step = pattern length |
| ◀ / ▶ | steps 1–32 / 33–64 | — | — |
| Clear | — | — | + step = clear step; + track = clear pattern |
| Mutation | shuffle the selected track's part | — | long press: back to the original |
| Probability | open / close the probability page (8 steps as bars; ◀ / ▶ = next 8) | — | — |
| Patterns | open / close the pattern view (top rows = 16 patterns: switch, chain, + Duplicate copy, + Clear clear) | — | same, closes when released |
| Duplicate | — | — | + step = copy it, then + steps = paste |
| Projects | save | — | top rows = 32 projects: switch |
| Note | back to note mode (playback continues) | — | — |

---

## Installing

> [!WARNING]
> **Early beta.** This firmware has been tested on very few devices. Flashing your own Launchpad is at your own
> risk: the firmware may misbehave or lose your projects and settings, and an interrupted or failed update can leave
> the Launchpad needing recovery from the bootloader. The authors accept no responsibility for damage to your device
> or data. It is not Novation software and Novation does not support it.

No Novation firmware is included in this project.

1. Get the firmware: download the latest `.syx` from the
   [releases page](https://github.com/cyberheater/Launchpad-Pro-MK3-Custom-firmware/releases), or build it yourself with
   `cargo lppmk3` in [cyberheater/Launchpad-Pro-MK3-Custom-firmware](https://github.com/cyberheater/Launchpad-Pro-MK3-Custom-firmware)
   (branch `lppmk3-sequencer`), which makes `build/lppmk3/fw.syx`.
2. Unplug the Launchpad. Hold **Setup** while plugging the USB cable back in: the Launchpad starts in bootloader
   mode and a MIDI port with "Bootloader" in its name appears.
3. Send the `.syx` to that port, using any one of:
   - CoreFW's `python3 tools/flash.py <file>.syx` (needs `pip install mido python-rtmidi`),
   - on a Mac, `swift scripts/flash_syx.swift <file>.syx` from this repository,
   - any SysEx tool (SysEx Librarian on macOS, MIDI-OX on Windows).

   Do not unplug the Launchpad while it is sending.
4. The Launchpad restarts with the new firmware. Press **Sequencer** to open it.

**Going back to the stock firmware**: enter bootloader mode the same way and update it with Novation Components.

Projects are stored in a separate flash area from the firmware, so updating the sequencer firmware should keep
them. The first time this version opens, it converts the 8 projects of earlier versions into projects 1–8: each
track's patterns A–H become patterns 1–8, and every track starts on track 1's pattern.
