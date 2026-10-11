# Helpers for a scripted terminal demo, sourced by a bash scene script recorded with asciinema.
# They type each command with fish's syntax highlighting (Catppuccin Macchiato), then run it for
# real after the person's starship prompt. DEMO_PROMPT_DIR sets the directory whose prompt is
# shown (default: the current one).

# The starship prompt as fish shows it, minus the leading clear and the right-side fill; a plain
# green arrow without starship.
if command -v starship >/dev/null; then
  demo_prompt=$(cd "${DEMO_PROMPT_DIR:-$PWD}" \
    && STARSHIP_SHELL=fish starship prompt --status 0 --cmd-duration 0 --terminal-width 200 \
    | perl -0pe 's/^\e\[J\n//; s/\e\[30m +\e\[0m/\e[0m/'; printf x)
  demo_prompt=${demo_prompt%x}
else
  demo_prompt=$'\e[1;32m❯\e[0m '
fi
prompt() { printf '%s' "$demo_prompt"; }

# fish wraps grep with --color=auto; do the same so matches show in red.
grep() { command grep --color=auto "$@"; }

c_cmd=$'\e[38;2;138;173;244m' c_opt=$'\e[38;2;166;218;149m' c_end=$'\e[38;2;245;169;127m'
c_arg=$'\e[38;2;240;198;198m' c_com=$'\e[38;2;128;135;162m' c_key=$'\e[38;2;237;135;150m'
c_off=$'\e[0m'

# type_cmd CMD: prints CMD one character at a time, each token in fish's color: the command blue,
# options and quotes green, `|` peach, `time` red, arguments flamingo and underlined when they
# name a file, comments grey.
type_cmd() {
  local rest=$1 tok color first=1 i
  while [ -n "$rest" ]; do
    if [[ $rest =~ ^\ + ]]; then tok=${BASH_REMATCH[0]} color=
    elif [[ $rest =~ ^#.* ]]; then tok=${BASH_REMATCH[0]} color=$c_com
    elif [[ $rest =~ ^\'[^\']*\' ]]; then tok=${BASH_REMATCH[0]} color=$c_opt
    elif [[ $rest =~ ^\| ]]; then tok='|' color=$c_end first=2
    else
      [[ $rest =~ ^[^\ \|]+ ]]
      tok=${BASH_REMATCH[0]}
      if [ "$first" != 0 ] && [ "$tok" = time ]; then color=$c_key first=2
      elif [ "$first" != 0 ]; then color=$c_cmd
      elif [[ $tok == -* ]]; then color=$c_opt
      elif [ -e "$tok" ]; then color=$c_arg$'\e[4m'
      else color=$c_arg
      fi
    fi
    rest=${rest:${#tok}}
    if [ "$first" = 2 ]; then first=1; elif ! [[ $tok =~ ^\ +$ ]]; then first=0; fi
    for ((i = 0; i < ${#tok}; i++)); do
      printf '%s%s%s' "$color" "${tok:i:1}" "$c_off"
      sleep "0.0$((RANDOM % 41 + 30))"
    done
  done
}

# run CMD [PAUSE]: types CMD, runs it, then pauses so the output can be read (default 2 s).
run() {
  prompt
  sleep 0.5
  type_cmd "$1"
  sleep 0.3
  printf '\n'
  eval "$1"
  printf '\n'
  sleep "${2:-2}"
}

# comment TEXT: types a `# ...` line, as if entered at the prompt.
comment() {
  prompt
  sleep 0.4
  type_cmd "$1"
  printf '\n\n'
  sleep 0.3
}
