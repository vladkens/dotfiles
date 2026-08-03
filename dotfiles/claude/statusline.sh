#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
get() { jq -r "$1" <<<"$input"; }

fmt_tokens() {
  awk -v n="$1" 'BEGIN {
    if      (n >= 1000000) printf "%.1fM", n / 1000000
    else if (n >= 1000)    printf "%.0fK", n / 1000
    else                   printf "%d",    n
  }'
}

model="$(get '.model.display_name')"
dir="$(get '.workspace.current_dir')"
dir="${dir/#"$HOME"/\~}"

context_remaining="$(get '(.context_window.remaining_percentage // 100)')% left"
five_hour="$(get '(100 - .rate_limits.five_hour.used_percentage) | round')%"
weekly="$(get '(100 - .rate_limits.seven_day.used_percentage) | round')%"
window="$(fmt_tokens "$(get '.context_window.context_window_size')")"
used="$(fmt_tokens "$(get '.context_window.context_window_size * .context_window.used_percentage / 100')")"

# printf '%s · %s · Context %s · 5h %s · weekly %s · %s window · %s used\n' \
  # "$model" "$dir" "$context_remaining" "$five_hour" "$weekly" "$window" "$used"

printf '%s · %s · Context %s · 5h %s · weekly %s\n' "$model" "$dir" "$context_remaining" "$five_hour" "$weekly"
