<img src="app/icon/icon.png" width="128" align="right" alt="App icon">

# Launchpad Pro MK3 emulator (Renode)

> **No firmware is included.** Bring your own: build [CoreFW](https://github.com/anthonyhfm/launchpad-core-firmware)
> (`cargo lppmk3`), or use your own copy of Novation's official Launchpad Pro MK3 update file (`.syx`). Novation
> firmware must not be committed to this repository.

Goal: test new firmware (CoreFW + 8-track sequencer) before flashing real hardware.
The stock Novation firmware is used as a calibration check of the hardware model.

## Layout
- This folder is a git repository; `corefw/` is excluded because it is its own clone (sequencer work on its
  branch `lppmk3-sequencer`). Clone it with `git clone https://github.com/anthonyhfm/launchpad-core-firmware corefw`.
- `corefw/` — clone of https://github.com/anthonyhfm/launchpad-core-firmware (branch `code`)
- `renode/lppmk3.repl` — platform: Renode STM32F746 model, resized to the F745VE
  (512 KB flash, 320 KB RAM), plus UART4/UART5
- `renode/boot.resc` — loads an ELF, sets VTOR/SP/PC from 0x08010000 like the bootloader,
  runs N virtual seconds and reports where the CPU ended up
- `tools/` — Renode 1.17.0 dmg (app installed at ~/Applications/Renode.app)

## Mac app (`app/`) — recommended
Native SwiftUI app "LPP MK3 Emulator": hardware-style front panel connected to the M0 model inside Renode
(`renode/LPPM0.cs`, via its front-panel socket); manages a bundled Renode process (free ports chosen at launch).
```bash
cd app && ./make_app.sh            # -> app/build/LPP MK3 Emulator.app (~180 MB, Renode inside)
./make_app.sh --no-renode          # small dev build, uses ~/Applications/Renode.app
open "build/LPP MK3 Emulator.app"
```
- **Firmware menu**: Open Firmware…, **Firmware Library…** (⌘L: every known firmware with type, version, date;
  Load / Show in Finder / Copy into Library / Remove; drop files in to add them), the latest **CoreFW build** (⌘1 ELF,
  ⌘2 .syx; folder found next to the app's checkout or set with Set CoreFW Folder…), library copies and recent files.
  The library folder is `~/Library/Application Support/LPP MK3 Emulator/Firmware`.
- File ▸ Open Firmware… (⌘O): CoreFW ELF (`corefw/target/thumbv7em-none-eabihf/release/core`), raw `.bin`
  (loaded at 0x08010000) or a `.syx` update file (decoded in-app; decoder verified byte-identical to Python).
- Emulator ▸ Restart (⌘R) / Stop (⌘.), CPU rate after boot, Show Renode Log, Show Workspace.
- Reopens the last firmware on launch from a cached copy in the workspace (avoids the macOS folder-access prompt
  that blocked launch after rebuilds); ⌘R re-reads the original file, so a fresh CoreFW build is picked up. Generated files + `renode.log`: `~/Library/Caches/local.lppemu/`.
- Click = hard press, ⌥-click = soft, ⇧-click = latch. Holding Setup opens the CoreFW setup menu.
- **USB MIDI:** the firmware's USB-MIDI ports appear in CoreMIDI as virtual ports named after its jacks plus
  " (Emu)" — stock 4.40: `LPProMK3 MIDI (Emu)`, `LPProMK3 DIN (Emu)`, `LPProMK3 DAW (Emu)`; CoreFW: `Port 1/2 (Emu)`.
  Use them from Logic/Ableton like the real device. The status bar shows the port count once enumerated.
- **Real Launchpad (Hardware menu):** when a Launchpad Pro MK3 running Novation's firmware is connected over USB, the
  app finds its "LPProMK3 MIDI" port, switches it to Programmer mode, mirrors every emulator LED onto it (RGB SysEx,
  batched every ~8 ms) and feeds its pads and buttons (with velocity and aftertouch pressure) into the emulated
  Launchpad. Unplugging, quitting or unticking *Mirror on Connected Launchpad* returns it to its normal mode.
  Verified with a real Pro MK3 (2026-11-07). Setup and Shift may not be reported in Programmer mode (not yet checked).
- **MIDI menu — DIN jacks to real devices:** *DIN Out 1 →*, *DIN Out 2 →* and *DIN In ←* each pick any MIDI device on
  the Mac (USB-MIDI interface, a synth's USB port, the real Launchpad's "LPProMK3 DIN" port…), or None (default).
  With a two-port interface the two outputs stay separate; if both go to one device, clock is sent once. Choices are
  kept by CoreMIDI ID and name, so devices reconnect when plugged back in. Verified 2026-11-07: sequencer → PreSonus
  Studio 24c MIDI Out → keyboard, clean (also a test MIDI device, and the real Launchpad's jack).
  Caveat for the Launchpad's own "LPProMK3 DIN" port: Novation's firmware echoes every pad press (its Programmer-mode
  note, plus aftertouch) out of its DIN jack, which clashes with the emulator's notes; no SysEx turns that off
  (scanned all commands, also DAW mode). Use a separate MIDI interface for clean results.
- **DIN MIDI:** CoreMIDI sources `LPP Emu DIN Out 1` / `LPP Emu DIN Out 2` carry what the firmware sends on the two
  DIN outputs; destination `LPP Emu DIN In` feeds the DIN input. Route them to/from your synths in a DAW or with
  Audio MIDI Setup to test per-port routing without hardware.
- App icon: drawn in code by `app/icon/make_icon.swift` (the sequencer's 8 track colours, white playhead);
  `make_app.sh` renders all sizes into `AppIcon.icns` via `app/icon/make_icns.sh`.
- Rebuild the app after changing anything in `renode/` (the platform files are copied into the bundle).
- The app kills any Renode left over from a force-quit before starting a new one.

## Run (interactive, with front panel) — scripts, no app
```bash
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
cd corefw && cargo lppmk3 && cd ..
~/Applications/Renode.app/Contents/MacOS/renode --disable-gui -P 1234 -e 'include @renode/run.resc' &   # any folder
cd ../m0 && python3 -I panel_bridge.py
```
Open http://localhost:8765. Click = hard press, Option-click = soft, Shift-click = latch. Hold Setup (Shift-click it) for the CoreFW setup menu.
`python3 renode/mon.py 'mach set 0' 'machine GetTimeSourceInfo'` queries the running Renode.
Another firmware: `-e '$elf=@/path/fw.elf; include @run.resc'`.

## Boot test (headless, N virtual seconds)
`renode --console --disable-gui -e '$seconds="5"; include @boot.resc' < /dev/null`

## M0 model (`renode/LPPM0.cs`, inside Renode)
Renode peripheral `m0` (debug registers at 0x5FF00000: frames, pings, commits, overruns, unknown, streaming),
attached to UART5. Emulates the stock M0 protocol (ping BB, button frames AA, LEDs 55/88, brightness 66/77) and
the STM32 ROM bootloader subset CoreFW probes with.
- Button frames stream on a **virtual-time** timer (`m0 StreamPeriodUs`, default 2000), so pauses or slow host
  time no longer break the link. Replies (BB, CoreFW single frames, ROM) come after `m0 ReplyDelayUs` (100).
- **Overrun:** if the firmware has not drained the previous frame (UART5 not empty), the frame is dropped and
  counted, instead of piling up in Renode's unbounded USART queue.
- `m0 StreamUpMips N` raises the CPU rate once the stream is up (run.resc: `$runmips`, default 216).
- Front panel: `m0 StartPanel <port>` opens a TCP text socket (one client; a new one replaces the old):
  in `p <control> <pressure>` / `?`; out `l <hwLed> r g b`, `s frames pings commits overruns unknown streaming`, `up`.
- `m0/panel_bridge.py` serves the browser panel (`panel.html`) on :8765 from that socket. Index maps from CoreFW `map.rs`.

## Status (2026-11-06)
| Firmware | Result after 2 virtual s | Host time |
|---|---|---|
| CoreFW (build 999) | Clocks, caches, SPI flash init OK; waits in `M0Link::roadrunner_version_inquiry` | 57 s (busy-polling UART) |
| Stock 4.40 | FreeRTOS scheduler up, all tasks blocked, idle task running; polls M0 with `0xBB` on UART5 | 4.4 s |

**Update:** with the M0 model, CoreFW completes the handshake, streams button frames over UART5+DMA1 S0
and drives LEDs; the Setup menu works. Stock 4.40 not yet re-tested with the M0 model.

## Stock 4.40 firmware status (2026-11-07)
- Boots to its start-up animation and **Note mode**; **pads work** (pressed pad + duplicate note light green).
- **Side buttons work** (verified 2026-11-07 after the M0 move: Chord, Sequencer, Session, Note switch modes;
  holding a mode button previews it and releasing returns, as on hardware — a quick tap switches). The earlier
  "side buttons don't work" was the broken M0 link, not missing hardware. They come from the M0 frame like CoreFW:
  TIM3 (PSC 107, ARR 4974 → 5 ms, IRQ 29) signals a relay thread, which signals the button-scan thread; that
  copies the 8 side-button bytes from the RX frame (0x20002cd0+0x84) to 0x20002868, ORs in Setup/Shift GPIO
  (byte 1 bits 6/7), and debounces 42 entries `{state, byte, mask, count}` at 0x200027c0 (4 ticks). Entry order:
  frame byte 0 bit 0/1 = Left/Right, byte 2 = Session/Note, byte 4 = Chord/Custom, byte 6 = Sequencer/Projects, ...
  Events go to the shared control queue 0x20049100.
- After ~10 min idle the stock firmware plays a full-surface colour-cycling animation (any input wakes it).
- Stock M0 protocol differences vs CoreFW: `AA 01 FF FF` = continuous button stream (CoreFW uses `AA 01 01 00`
  per frame); a `BB` ping returns the M0 to its handshake state; the firmware arms RX DMA *after* sending, and
  re-arms normal-mode DMA from its ISR after every 140-byte frame, so frames need gaps.
- M0Rx state machine: state byte `0x2004924f` (0 ping, 1 wait BB, 2 start stream, 3 streaming), RX buffer
  `0x20002cd0`.
- **Fixed (2026-11-07):** the link used to desync after any hiccup because the stream was paced by host time and
  frames piled up in Renode's USART queue. With the M0 inside Renode (virtual-time stream, drop on overrun) the
  stock firmware stays in state 3 with 0 overruns, survives a 3 s `pause`, and pads light and clear correctly.
  (A runtime-compiled USART copy also fixed overrun but made per-byte RX ~5x slower; avoid such hot paths.)

## USB (`renode/LPPOTGFS.cs`)
STM32F7 OTG FS core (Synopsys DWC2, device mode, FIFO/slave mode) with a built-in USB host acting as the Mac:
bus reset → ENUMDNE → GET_DESCRIPTOR device/config/strings (incl. MIDI jack names) → SET_ADDRESS →
SET_CONFIGURATION, then USB-MIDI bulk IN/OUT, all in virtual time. Works with ST's HAL PCD (stock) and CoreFW's
`otg_fs.rs`; both enumerate as `1235:0123 "Launchpad Pro MK3"`, MIDI on EP1 IN/OUT.
- Bridge socket `usbOtgFs StartBridge <port>` (run.resc: 3457), text lines: out `dev vid pid name`,
  `cable in|out n name`, `ready`, `m xxxxxxxx` (one USB-MIDI packet), `log …`; in `m xxxxxxxx`.
- `usbOtgFs Status` in the monitor shows host state and packet counts.
- Verified: stock pad → note on/channel pressure/note off; note in lights pads; Universal Device Inquiry returns
  Novation 00 20 29, family 23 01, version 0440; stock sends MIDI clock on cable 0. CoreFW pads send notes on
  cable 1, notes into cable 1 light pads.
- Not modelled: DMA mode, isochronous endpoints, suspend/resume, SOF interrupts.

## DIN MIDI (`renode/LPPDIN.cs`)
Found by tapping every UART on stock 4.40: **UART4 = DIN Out 1 + DIN In** (CR1 RE/TE/RXNEIE), **UART7 = DIN Out 2**
(TX+RX enabled, no RX interrupt); both BRR 0x6B7 = 31250 baud at 54 MHz. Stock mirrors MIDI clock and the USB "DIN"
cable (cable 1) to both outs; bytes on DIN In are forwarded to USB cable 1; a SysEx device inquiry on DIN In is
answered on Out 1 only. (Which physical jack is "Out 1" vs "Out 2" is inferred, not checked on hardware.)
- `din StartBridge <port>` (run.resc: 3458), text lines: out `o <1|2> <hex>` per byte; in `i <hex bytes…>`
  (fed to UART4's receiver, paced at the UART's baud rate in virtual time).
- The app parses the byte streams (running status, SysEx, real-time) into CoreMIDI messages (`MIDIUMP.swift`).

## SPI flash (`renode/LPPSpiFlash.cs`)
16 MB Macronix-style NOR flash (JEDEC C2 20 18) on SPI1, chip select PA15. 25-series commands (9F, 05, 06/04, 03/0B,
02, 20/52/D8, 60/C7). Contents persist in a file: run.resc uses `renode/flash.bin` (`$flash`), the app uses
`~/Library/Caches/local.lppemu/flash.bin`. CoreFW now finds its flash (settings persist too). The stock 4.40 firmware
boots normally with it present.

## Speed / timing (fixed 2026-11-06)
- **Runs at 1.000x real time** after boot (Renode keeps virtual time locked to the host clock).
  Boot to a live button stream: ~11 s.
- Timer kernel clocks set to the real 108 / 216 MHz (Renode default 10 MHz made firmware time 10.8x slow).
- `STM32_TimerLP.cs`: patched copy of Renode's STM32_Timer — a compare at CCRx = 0 now fires on counter
  wrap. Upstream never fired it, so embassy-time alarms on a 2-second boundary were lost and CoreFW froze
  ~20 s after boot. All 14 timers use it (`stm32f745_base.repl` is Renode's F746 file with that swap).
- CPU rate: boots at `$bootmips` (50) because boot only busy-waits on timeouts; the M0 model switches to
  `$runmips` (216 = 216 MHz at 1 instr/cycle) once its button stream is up.
- Measured 2026-11-07 (8 tracks x 8-note chords playing): at 216 MIPS the emulator manages only ~0.55-0.63x real
  time (tempo ~75 BPM for 120, occasional 25 ms hiccups); the firmware mostly busy-waits for the M0 reply. 100 MIPS is
  the lowest rate at which the M0 link (pads, LEDs) still works — at 75 and below the LED/button window is missed —
  and keeps 1.0x real time (120.0 BPM, beats within ±4 ms). The app defaults to 100 (Emulator ▸ CPU rate, remembered);
  `RUNMIPS=n ./run_tests.sh` runs the suite at another rate.
- Caveat: Renode syncs to the host clock cumulatively, so after boot it runs up to ~1.25x fast for
  ~20-30 s to recover the time lost while booting. Wait that long before timing-sensitive tests.
- Tools: `renode/sample.py N elf` (PC-sampling profiler + real-time ratio), `renode/mon.py` (monitor).

## Hardware the firmware touches that is not modelled yet
- ~~UART5 ↔ M0 co-processor~~ — done (`renode/LPPM0.cs`).
- ~~USB OTG FS~~ — done (`renode/LPPOTGFS.cs`).
- **Performance** — CoreFW busy-polls MMIO; Renode handles that slowly.
- ~~SPI1 external flash~~ — done (`renode/LPPSpiFlash.cs`).
- ~~DIN MIDI~~ — done (`renode/LPPDIN.cs`, UART4 Out 1 + In, UART7 Out 2). CoreFW has no MK3 DIN driver yet.
- **CRC unit** @0x40023000 (stock uses hardware CRC), DMA FIFO/error-flag bits, RCC 0x90.

## 8-track sequencer (CoreFW, `corefw/src/app/sequencer/`) — Pro MK3 only, uncommitted
Full control reference: the comment at the top of `corefw/src/app/sequencer/mod.rs`. Hardware test sheet:
`HARDWARE_TEST.md`. Opened with the **Sequencer** button from note mode; **Note** returns; playback continues in the
background (Sequencer button green in note mode).
- **Tracks**: 8, each with MIDI channel, output (USB / DIN 1 / DIN 2 / DIN 1+2), mute and transpose (hold a track button).
- **Patterns**: 8 per track × 32 steps, length per pattern. Hold Patterns (89): tracks × patterns grid; tap to switch
  (queued to the end of the pattern while playing); hold + tap to chain; Duplicate/Clear + tap to copy/clear.
- **Steps**: up to 8 notes (a chord: hold a step, tap note pads; the first tap sets the note, later taps add or
  remove notes), velocity (right column while holding a step), gate in eighths (bottom row), probability
  (Shift + right column). Swing 50-75 % (Shift + step pads), timed to the millisecond.
- **Live recording**: tap Record (bottom-left) to arm; while playing, notes from the pads or from a keyboard (USB MIDI
  port / DIN In) land on the nearest step of the selected track with their velocity and held length; notes played
  together are recorded as a chord. The app's DIN In defaults to "All MIDI inputs" (notes only, no clock — a keyboard
  with MIDI Thru would echo the sequencer's clock back); pick a single input to follow an external clock.
- **MIDI thru**: a keyboard on the USB MIDI port / DIN In plays the selected track (notes, aftertouch, controllers,
  program change, pitch bend re-sent on that track's output and channel); echoes from a keyboard with MIDI Thru are
  recognised and dropped.
- **Clock**: internal (Shift + Up/Down = tempo) or external MIDI clock from the USB MIDI port or DIN In (auto-follow,
  clock passed on to both DIN outs, Play LED cyan); falls back to internal 500 ms after the last pulse.
- **Projects**: 8 slots in flash (tap Projects = save, hold = slot row); v4 format (8 notes per step) at user offset 0x80000,
  32 KB per slot, CRC-32, last slot auto-loaded; v3/v2 saves (16 KB slots at 0x40000) and v1 saves load too.
- **Drivers**: `din.rs` — DIN Out 1 = UART4 TX PA0, DIN Out 2 = UART7 TX PE8, DIN In = UART4 RX PC11 (all AF8,
  31250 8N1, interrupt-driven rings, running-status/SysEx parser), copied from stock 4.40's setup. Outputs send
  running status (note-off velocity 0 as note-on velocity 0), queue whole messages only (a full 2 KB ring drops a
  message, never part of one), so 8 tracks x 8-note chords degrade to late notes rather than stuck ones. One DIN out
  carries ~1500 notes/s with running status: spread busy tracks across DIN 1 and DIN 2.
  `MidiPort::Din2`; `read/write_user_storage` on the external flash (1 MB at 0xF00000).
- **Tests** (`renode/`): `run_tests.sh [elf|bin|syx]` runs seqtest, bgtest, exttest, dinintest, veltest, swingtest, rectest,
  chordtest, thrutest, flashtest and pattest, each on a fresh boot, with save/restart checks. Output of the last run: `renode/regression.txt`.

## Update image format (verified on stock 4.40 and CoreFW)
SysEx `F0 00 20 29 00 <cmd>`: 71 header, 7C version + nibble size + CRC, 72 data, 73 = block 0 sent last.
Block = 37 septets → big-endian 259-bit int >> 3 → 32 bytes. Header CRC = CRC-32/MPEG-2 of the full
0x70000 image. Image trailer (last 8 bytes) = 4-byte version + LE CRC-32/MPEG-2 of image[:-8].
