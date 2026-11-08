#!/bin/zsh
# Regression tests for the CoreFW sequencer in the emulator.
# usage: [RUNMIPS=n] ./run_tests.sh [firmware]   firmware = CoreFW ELF (default: corefw release build), .bin, or .syx
# Each test boots a fresh emulator with an empty flash; pattest also restarts it to check save/reload.
cd "${0:A:h}"
fw=${1:-../corefw/target/thumbv7em-none-eabihf/release/core}
decoder="../app/build/LPP MK3 Emulator.app/Contents/MacOS/LPPEmu"
case "$fw" in
  *.syx) "$decoder" --decode "$fw" _tests_fw.bin || exit 1; load="sysbus LoadBinary @$PWD/_tests_fw.bin 0x08010000" ;;
  *.bin) load="sysbus LoadBinary @${fw:A} 0x08010000" ;;
  *)     load="sysbus LoadELF @${fw:A}" ;;
esac
# RUNMIPS=n ./run_tests.sh ... runs the firmware at n MIPS after boot (default 216, the real chip's rate)
sed -e "s|^sysbus LoadELF \$elf|$load|" -e 's|^\$flash?=.*|$flash?=$ORIGIN/_tests_flash.bin|' \
    -e "s|^\$runmips?=.*|\$runmips?=${RUNMIPS:-216}|" run.resc > _tests.resc

boot() {
  pkill -f "renode --disable-gui -P 1234"; sleep 2
  ~/Applications/Renode.app/Contents/MacOS/renode --disable-gui -P 1234 -e "include @_tests.resc" > _tests.log 2>&1 &!
  for i in {1..60}; do python3 -I mon.py 'mach set 0' 'usbOtgFs Status' 2>/dev/null | grep -q "cfg=True" && break; sleep 2; done
  sleep 12
}

run() {   # run <test.py> [args...]  (fresh flash)
  rm -f _tests_flash.bin; boot
  echo "=== $*"; python3 -I "$@"
}

run seqtest.py
run bgtest.py
run exttest.py
run dinintest.py
run veltest.py
run swingtest.py
run rectest.py
run chordtest.py
run thrutest.py
run echotest.py
run tempotest.py
run clocktogtest.py
run ratetest.py
run flashtest.py program; boot; echo "=== flashtest.py verify (after restart)"; python3 -I flashtest.py verify
run pattest.py program;   boot; echo "=== pattest.py verify (after restart)";   python3 -I pattest.py verify
run steptest.py program;  boot; echo "=== steptest.py verify (after restart)";  python3 -I steptest.py verify
pkill -f "renode --disable-gui -P 1234"
rm -f _tests.resc _tests.log _tests_flash.bin _tests_fw.bin
