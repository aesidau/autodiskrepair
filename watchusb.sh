#!/bin/zsh
HOST="192.168.0.38"
USER="pi"
SOUND1="/System/Library/Sounds/Ping.aiff"
SOUND2="/System/Library/Sounds/Submarine.aiff"

# This line is needed for line stripping logic
setopt extendedglob

# Have the drives already appeared at startup?
# Pass "ready" (or 1/yes/true) as the first argument in cases where you
# start the log monitor after the drives have already appeared.
# Default is to assume that devices for drives have not appeared yet
drives_ready=0
case "$1" in
  ready|1|yes|true) drives_ready=1 ;;
esac

ssh -l "$USER" -t "$HOST" 'sudo dmesg --follow-new' | \
while IFS= read -r line; do
  printf '%s\n' "$line"
  clean=${line//$'\e'\[[0-9;]#m/}  # strip ANSI colour/formatting codes
  clean=${clean%$'\r'}             # strip trailing CR from the PTY

  case "$clean" in
    *"reset high-speed USB device number"*"using dwc_otg"*)
      if (( drives_ready )); then
        afplay "$SOUND1" & 
        ssh -n -l "$USER" "$HOST" 'sudo pkill -INT -x ddrescue'
        sleep 3
        ssh -n -l "$USER" "$HOST" 'cd ~/autodiskrepair && python plug.py off > /dev/null' 
        drives_ready=0
      fi ;;
    *"]  sd"[bcd]": sd"[bcd]"1 sd"[bcd]"2"*)
      afplay "$SOUND2" & 
      drives_ready=1 ;;
  esac
done

# Note: drives_ready value will not reflect while loop state at this point
