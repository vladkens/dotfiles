#!/usr/bin/env bash
# Usage: play-cast.sh CAST [WIDTH HEIGHT]
#
# Plays an asciinema recording in the frontmost terminal window for a screen recording. Sets the
# window to WIDTH×HEIGHT points (default 966×585: 120×32 cells in Ghostty at 13 pt) and the
# largest font at which the recording's columns and rows still fit, clears the screen and waits
# 3 s: start recording the window then. No playback banner. Cmd+0 resets the font afterwards.
# Needs Accessibility access for the terminal (System Events keystrokes).
set -eu
cast=$1 width=${2:-966} height=${3:-585}
need_cols=$(head -1 "$cast" | jq '.term.cols // .width')
need_rows=$(head -1 "$cast" | jq '.term.rows // .height')

key() { osascript -e "tell application \"System Events\" to keystroke \"$1\" using command down"; }
fits() {
  local rows cols
  read -r rows cols < <(stty size < /dev/tty)
  [ "$cols" -ge "$need_cols" ] && [ "$rows" -ge "$need_rows" ]
}

app=$(osascript -e 'tell application "System Events" to name of first process whose frontmost is true')
osascript -e "tell application \"System Events\" to tell process \"$app\" to set size of front window to {$width, $height}"
key 0
sleep 0.4
for _ in $(seq 15); do
  key =
  sleep 0.4
  fits || { key -; sleep 0.4; break; }
done
fits || echo "the window holds $(stty size < /dev/tty) (rows cols), the recording needs $need_rows $need_cols" >&2

printf '\e[H\e[2J'
sleep 3
asciinema play -q "$cast"
sleep 3
