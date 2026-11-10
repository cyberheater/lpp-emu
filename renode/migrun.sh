#!/bin/zsh
# Old-format conversion test: the old firmware saves projects, then the new one converts them.
# usage: ./migrun.sh <old firmware ELF> [new firmware ELF]
cd "${0:A:h}"
old=${1:?old firmware ELF}; new=${2:-../corefw/target/thumbv7em-none-eabihf/release/core}
mk() { sed -e "s|^sysbus LoadELF \$elf|sysbus LoadELF @${1:A}|" -e 's|^\$flash?=.*|$flash?=$ORIGIN/_mig_flash.bin|' \
          -e "s|^\$runmips?=.*|\$runmips?=216|" run.resc > _mig.resc; }
boot() {
  pkill -f "renode --disable-gui -P 1234"; sleep 2
  ~/Applications/Renode.app/Contents/MacOS/renode --disable-gui -P 1234 -e "include @_mig.resc" > _mig.log 2>&1 &!
  for i in {1..60}; do python3 -I mon.py 'mach set 0' 'usbOtgFs Status' 2>/dev/null | grep -q "cfg=True" && break; sleep 2; done
  sleep 12
}
rm -f _mig_flash.bin
mk "$old"; boot; echo "=== migtest.py old"; python3 -I migtest.py old
mk "$new"; boot; echo "=== migtest.py new"; python3 -I migtest.py new
pkill -f "renode --disable-gui -P 1234"
rm -f _mig.resc _mig.log _mig_flash.bin
