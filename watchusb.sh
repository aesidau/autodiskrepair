#!/bin/zsh
HOST="192.168.0.38"
USER="pi"
SOUND1="/System/Library/Sounds/Ping.aiff"
SOUND2="/System/Library/Sounds/Submarine.aiff"

setopt extendedglob

ssh -l "$USER" -t "$HOST" 'sudo dmesg --follow-new' | \
while IFS= read -r line; do
  printf '%s\n' "$line"
  clean=${line//$'\e'\[[0-9;]#m/}  # strip ANSI colour/formatting codes
  clean=${clean%$'\r'}             # strip trailing CR from the PTY

  case "$clean" in
    *"reset high-speed USB device number"*"using dwc_otg"*)
      afplay "$SOUND1" & 
      ssh -n -l "$USER" "$HOST" 'sudo pkill -INT -x ddrescue'
      sleep 3
      ssh -n -l "$USER" "$HOST" 'cd ~/autodiskrepair && python plug.py off > /dev/null' ;;
    *"]  sd"[bcd]": sd"[bcd]"1 sd"[bcd]"2"*)
      afplay "$SOUND2" & ;;
  esac
done

