# Testing the 8-track sequencer firmware on a real Launchpad Pro MK3

Everything below has passed in the emulator (`renode/run_tests.sh`, see `renode/regression.txt`). These are the
steps and checks only real hardware can confirm.

## Files
| File | What |
|---|---|
| `corefw/build/lppmk3/fw.syx` | CoreFW + sequencer, version 999. Rebuild with `cd corefw && cargo lppmk3`. |
| Your own copy of Novation's official Launchpad Pro MK3 update (`.syx`) | To go back to stock. Not included in this repository. |

The `.syx` was checked to decode to exactly the image that was tested: only the CRC in the last 4 bytes differs from
`fw.bin`, which is expected.

## Before flashing
- **Back up stock projects** you care about, with Novation Components. Where the stock firmware keeps its projects in
  flash is not known, and the sequencer saves to the 1 MB area at 15 MB (0xF00000). That area could overlap stock data.
- The Novation bootloader at 0x08000000 is never written by firmware updates, so you can always get back.

## Flash
1. Quit the emulator app (it mirrors onto the Launchpad).
2. Unplug the Launchpad. Hold **Setup** and plug USB back in: this is bootloader mode (on the Pro MK3 it is Setup,
   not Capture MIDI as in CoreFW's generic readme). The Mac then shows "Launchpad Pro MK3 Bootloader LPProMK3 BL MIDI".
3. `swift scripts/flash_syx.swift corefw/build/lppmk3/fw.syx` (CoreMIDI, nothing to install; picks the port containing
   "Bootloader"). Or CoreFW's `python3 corefw/tools/flash.py corefw/build/lppmk3/fw.syx` (needs `mido python-rtmidi`).
4. The Launchpad reboots into CoreFW: its ports become "Launchpad Pro MK3 PRO MK3 (MIDI)" / "(DAW)".

First flashed onto real hardware 2026-11-07 (14,338 messages, about a minute): boots, sequencer works.

## Go back to stock (recovery)
Bootloader mode again (step 2: hold Setup while plugging in), then flash your Novation update file the same way, or with Novation
Components' firmware updater.

## Checks (in order; note anything that differs)
1. **Boots**: boot animation, then note mode; pads play notes over USB.
2. **Sequencer button** opens the sequencer: 32 dim step pads (top half), note pads (bottom half), coloured track row.
3. **DIN Out 1 vs 2**: track 1: hold its track button, tap note pad 2 (DIN 1); program steps 1/5/9/13; Play.
   Write down which physical jack sounds. Then pad 3 (DIN 2). *The emulator assumes UART4 = "Out 1" and UART7 = "Out 2";
   only this check confirms which is which.*
4. **DIN In**: send MIDI clock from a DIN device into MIDI In: the Play LED turns cyan and the sequencer follows.
5. **USB clock**: start a DAW with clock sent to "LPProMK3 MIDI": the sequencer follows start/stop/tempo.
6. **Save**: tap Projects (white flash, then green). Unplug, replug, open the sequencer: the pattern is back
   (Projects green).
7. **Patterns**: hold Patterns (top right). Tap B for track 1, add a step, hold A and tap B to chain. Play: A then B.
8. **Velocity / gate / probability**: hold a step: right column = velocity, bottom row = gate; + Shift = probability.
9. **Swing**: hold Shift: step pads show swing; tap pad 26 = 75 %.
10. **Background**: while playing, press Note: playback continues and the Sequencer button is green.
11. **Timing**: listen for steady timing at 120 BPM with all 8 tracks busy, and while saving (a short hiccup during a
    flash save is possible).

## Known gaps
- The stock flash layout is unknown (see "Before flashing").
- The DIN jack order is inferred (check 3).
- MIDI clock output runs whenever the sequencer plays. There's no setting to turn it off yet.
