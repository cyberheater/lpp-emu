#!/bin/zsh
# Restart Renode and report host seconds until the M0 model has sent >200 button frames.
# usage: ./boottime.sh   (leaves Renode running afterwards)
cd "${0:A:h}"
python3 -I mon.py quit >/dev/null 2>&1
for i in {1..40}; do pgrep -f 'MacOS/renode' >/dev/null || break; sleep 0.25; done
t0=$(perl -MTime::HiRes=time -e 'printf "%.2f", time')
~/Applications/Renode.app/Contents/MacOS/renode --disable-gui -P 1234 -e "include @run.resc" > run.log 2>&1 &!
while true; do
  sleep 0.5
  f=$(python3 -I probe.py 1 'sysbus ReadDoubleWord 0x5FF00000' 2>/dev/null | grep -oE '0x[0-9A-Fa-f]+$')
  [[ -n $f ]] && (( f > 200 )) && break
  now=$(perl -MTime::HiRes=time -e 'printf "%.0f", time')
  (( now - ${t0%.*} > 240 )) && { echo "timeout"; break; }
done
t1=$(perl -MTime::HiRes=time -e 'printf "%.2f", time')
echo "boot to >200 button frames: $(( t1 - t0 )) s host"
