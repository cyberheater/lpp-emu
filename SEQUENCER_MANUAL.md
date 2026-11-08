# Launchpad Pro MK3 Sequencer — User Manual

An 8-track step sequencer that runs on the Launchpad Pro MK3 itself, with no computer. Each track plays its own
part on its own MIDI channel, sent to USB, DIN Out 1, DIN Out 2 or both DIN outs.

| | |
|---|---|
| Tracks | 8, each with its own MIDI channel, output, octave range, transpose and step rate |
| Patterns | 8 per track (A–H), can be chained |
| Steps | up to 32 per pattern (16th notes) |
| Notes per step | up to 8 (chords) |
| Per step | velocity, gate length, probability |
| Global | tempo 30–300 BPM, swing 50–75 %, external MIDI clock sync |
| Projects | 8 save slots in the Launchpad's flash |

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
               Record Arm, Mute, Solo, Volume,        mutes 1 – 8
               Pan, Sends, Device, Stop Clip
```

- **Step area** (top four rows): the 32 steps of the selected track's current pattern. Lit = the step plays,
  brighter = louder. The playhead is shown as it moves.
- **Note area** (bottom four rows): 32 chromatic notes, lowest bottom-left. Tap one to hear it and to choose the
  note that new steps get.
- **Track select row**: the coloured buttons directly under the grid. Tap to select a track; hold for its settings.
- **Mute row**: the bottom row of buttons (Record Arm … Stop Clip) mutes tracks 1–8.

### Opening and leaving the sequencer

- **Sequencer** opens it. The first time after power-up, the last used project is loaded.
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

### Pattern length and clearing

| Action | Result |
|---|---|
| Hold **Fixed Length** + tap a step | The pattern ends at that step (1–32) |
| Hold **Clear** + tap a step | Clear that step |
| Hold **Clear** + tap a track button | Clear that track's current pattern |

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
Hold the track button and tap a pad in the third row of steps (straight rates green, triplets purple, chosen = bright):

| Pad | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|
| One step = | 1/32 | 1/16 triplet | **1/16 (default)** | 1/8 triplet | 1/8 | 1/4 triplet | 1/4 | 1/2 |
| Speed | 2× | 1.5× | 1× | ¾× | ½× | ⅜× | ¼× | ⅛× |

All tracks start together on Play, so they stay in line. Swing only affects tracks at 1/16; other rates play
straight. Gate lengths scale with the step; live recording uses the selected track's rate. Saved with the project.

**Mute**: tap a button in the bottom row (Record Arm = track 1 … Stop Clip = track 8).

---

## 4. Patterns and chaining

Each track has 8 patterns, A–H. Hold **Patterns** (top of the right-hand column): the grid becomes a pattern map,
one **column per track** (track 1 left) and one **row per pattern** (A at the top).

| Colour | Meaning |
|---|---|
| Track colour | the track's current pattern |
| Medium | part of the track's chain |
| Dim | has notes |
| White | queued (starts at the end of the playing pattern) |

| While holding Patterns | Result |
|---|---|
| Tap a pattern | Switch the track to it — at the end of the playing pattern, or at once when stopped |
| Hold one pattern + tap another in the same column | **Chain** the range (e.g. A–D plays A, B, C, D, A, …) |
| Hold **Duplicate** + tap a pattern | Copy the track's current pattern there |
| Hold **Clear** + tap a pattern | Clear that pattern |

Tracks can switch and chain independently, and patterns can have different lengths for polymeter.

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

**Play button colours**: green = playing on the internal clock, cyan = following an external clock.

---

## 6. Live recording

1. Tap **Record** (○, bottom of the left column) to arm it (dark red).
2. Press **Play**. While playing, Record is bright red.
3. Play notes on the note pads, or on a keyboard connected to the USB MIDI port or DIN In.

Notes land on the **nearest step** of the selected track's current pattern, with their velocity and their held
length as the gate (up to one step). Notes played together are recorded as a **chord** (up to 8; the loudest
velocity is kept). A note you play just ahead of a step is not replayed on that pass — you already heard it.

Tap Record again to disarm.

---

## 7. MIDI thru (playing from a keyboard)

A keyboard on the **USB MIDI port** or **DIN In** plays the **selected track**: notes, aftertouch, controllers,
program change and pitch bend are re-sent on that track's output and MIDI channel, whatever channel the keyboard
sends on. Select another track and the keyboard plays that one instead.

If your keyboard has its own sound, turn its **Local** setting off so you only hear the sound of the selected
track. Echoes from a keyboard with MIDI Thru switched on are recognised and dropped, so they do not loop or
double-record.

---

## 8. MIDI clock

**Sending**: when playing on its own clock, the sequencer sends MIDI clock, start and stop to USB and both DIN outs.

**Following an external clock**: clock, start, continue and stop arriving on the USB MIDI port or DIN In are
followed automatically. Play turns cyan, the external clock is passed on to both DIN outs, and tempo and tap tempo
have no effect. 500 ms after the last clock pulse the sequencer carries on with its own clock.

**Shift + Play** turns following an external clock on or off. While Shift is held, Play shows the setting:

| Play (Shift held) | Setting |
|---|---|
| Cyan | Follow an external clock (default) |
| Orange | Ignore incoming clock, start and stop; always run and send the sequencer's own clock |

The setting is saved with the project. Use *ignore* when a device on DIN In sends a clock you do not want to follow.

The sequencer also ignores its own clock coming back (a synth with MIDI Thru on DIN In), so the clock cannot run
away.

---

## 9. Projects (saving and loading)

| Action | Result |
|---|---|
| Tap **Projects** | Save to the current slot (the button flashes white) |
| Hold **Projects** | The track row shows the 8 slots: white = current, dim = saved, off = empty |
| Hold **Projects** + tap a slot | Load it (an empty slot just becomes the slot the next save goes to) |

The **Projects** button is **green** when everything is saved and **amber** when there are unsaved changes.

A project holds everything: all tracks, patterns, chains, channels, outputs, transpose, step rates, tempo, swing and the
external-clock setting. The last used slot loads automatically at power-up.

---

## 10. Quick reference

| Control | Alone | With Shift | Held + … |
|---|---|---|---|
| Step pad | toggle step | set swing | note pads = notes/chord, right column = velocity (+Shift = probability), bottom row = gate |
| Note pad | choose / preview note | — | — |
| Track button | select track | — | steps 1–16 = channel, steps 17–24 = step rate, note row 1 = output, rows 2–4 = transpose |
| Bottom row | mute track 1–8 | Sends = tap tempo | — |
| ▲ / ▼ | octave | tempo ±1 (±10 with Fixed Length) | (track held) channel ±1 |
| Play | start / stop | follow / ignore external clock | — |
| Record | arm recording | — | — |
| Fixed Length | — | — | + step = pattern length |
| Clear | — | — | + step = clear step; + track = clear pattern |
| Patterns | — | — | pattern map: switch, chain, + Duplicate copy, + Clear clear |
| Projects | save | — | track row = load slot |
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
them; projects saved by earlier sequencer versions load in later ones.
