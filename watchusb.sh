#!/bin/zsh
HOST="192.168.0.38"
USER="pi"
SOUND1="/System/Library/Sounds/Ping.aiff"
SOUND2="/System/Library/Sounds/Submarine.aiff"
HANG_TIMEOUT=150     # seconds of log silence to assume drive has hung
POLL=5               # how often (in seconds) to wake and check timer

# This line is needed for line stripping logic
setopt extendedglob
# This line is needed for detecting timeout
zmodload zsh/datetime

power_cycle() {
  afplay "$SOUND1" & 
  ssh -n -l "$USER" "$HOST" 'sudo pkill -INT -x ddrescue'
  sleep 3
  ssh -n -l "$USER" "$HOST" 'cd ~/autodiskrepair && python plug.py off > /dev/null' 
}

armed=0
deadline=0
# Have the drives already appeared at startup?
# Pass "ready" (or 1/yes/true) as the first argument in cases where you
# start the log monitor after the drives have already appeared.
# Default is to assume that devices for drives have not appeared yet
drives_ready=0
case "$1" in
  ready|1|yes|true) drives_ready=1 ;;
esac

ssh -l "$USER" -t "$HOST" 'sudo dmesg --follow-new' | \
while true; do
  t0=$EPOCREALTIME
  if IFS= read -r -t $POLL line; then
    last_activity=$EPOCREALTIME
    printf '%s\n' "$line"
    clean=${line//$'\e'\[[0-9;]#m/}  # strip ANSI colour/formatting codes
    clean=${clean%$'\r'}             # strip trailing CR from the PTY

    case "$clean" in
      *"reset high-speed USB device number"*"using dwc_otg"*)
        if (( $drives_ready )); then
          power_cycle
          armed=0
          drives_ready=0
        else
          armed=1
          # start the countdown for needing to power cycle
          deadline=$(( $EPOCHREALTIME + $HANG_TIMEOUT ))
        fi ;;
      *"]  sd"[bcd]": sd"[bcd]"1 sd"[bcd]"2"*)
        afplay "$SOUND2" & 
        drives_ready=1 
        armed=0 ;;
      *)
        armed=0 ;;  # any other message, things could be working fine
    esac
  else
    # read returned non-zero: a POLL timeout, or the stream closed
    (( $EPOCHREALTIME - t0 < $POLL * 0.5 )) && break    # instant return => ssh/dmesg ended
    if (( $armed && $EPOCHREALTIME >= $deadline )); then
      power_cycle
      armed=0
      drives_ready=0
    fi
  fi
done

# Note: drives_ready value will not reflect while loop state at this point
