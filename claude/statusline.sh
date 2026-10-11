#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
get() { jq -r "$1" <<<"$input"; }

rate_limit() {
  local key="$1" label="$2" format="$3" remaining reset timestamp
  remaining="$(get ".rate_limits.$key.used_percentage | numbers | 100 - . | round")"
  if [[ -z "$remaining" ]]; then
    return
  fi

  printf ' · %s %s%%' "$label" "$remaining"
  timestamp="$(get ".rate_limits.$key.resets_at | numbers | select(. > 0) | floor")"
  if [[ -z "$timestamp" ]]; then
    return
  fi

  reset="$(date -r "$timestamp" "+$format" 2>/dev/null || date -d "@$timestamp" "+$format" 2>/dev/null || true)"
  if [[ -n "$reset" ]]; then
    printf ' ↻ %s' "$reset"
  fi
}

model="$(get '.model.display_name')"
dir="$(get '.workspace.current_dir')"
dir="${dir/#"$HOME"/\~}"

context_remaining="$(get '(.context_window.remaining_percentage // 100)')% left"
printf '%s · %s · %s' "$model" "$dir" "$context_remaining"
rate_limit five_hour 5h '%H:%M'
rate_limit seven_day 7d '%d.%m %H:%M'
printf '\n'
