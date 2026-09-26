fish_add_path -g $HOME/.local/bin
fish_add_path -g /opt/homebrew/sbin
fish_add_path -g /opt/homebrew/bin
fish_add_path -g /opt/homebrew/opt/curl/bin

set -gx HOMEBREW_NO_AUTO_UPDATE 1
set -gx FZF_DEFAULT_COMMAND "fd --type file --color=always"
set -gx FZF_DEFAULT_OPTS "--ansi"

if not status is-interactive
	return
end

if test -f /opt/homebrew/opt/fzf/shell/key-bindings.fish
	source /opt/homebrew/opt/fzf/shell/key-bindings.fish
end

fish_config theme choose catppuccin-macchiato
if command -q tabs
	tabs -4
end

alias cat='bat --style=plain --paging=never'
alias ls='eza --group-directories-first'
alias ll='eza --all --long --group-directories-first'
alias ta='tmux new-session -A -s main'
alias gh-repo-open='gh repo view --web'
alias gh-pr-open='gh pr view --web'
alias gh-pr-checkout='gh pr checkout'

function reload --description 'Restart Fish and reload all configuration'
	exec fish
end

function fish_title
	prompt_pwd
end

if not functions -q __user_cd_original
	functions -c cd __user_cd_original
end

function cd --description 'Change directory with canonical path casing'
	if test (count $argv) -eq 1; and test "$argv[1]" != -
		set -l target (command realpath -- "$argv[1]" 2>/dev/null)
		if test $status -eq 0
			__user_cd_original -- "$target"
			return $status
		end
	end

	__user_cd_original $argv
end

if command -q starship
	starship init fish | source
end
