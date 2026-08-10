# top-level `set` is implicitly `-g`; use `-x` to pass env vars to subprocesses.
set -g fish_greeting
set -x LANG en_US.UTF-8

# --- PATH ---
fish_add_path -g $HOME/.local/bin
fish_add_path -g $HOME/.cargo/bin
fish_add_path -g $HOME/Library/Android/sdk/emulator

fish_add_path -g /opt/homebrew/opt/rustup/bin
fish_add_path -g /opt/homebrew/opt/mysql-client@8.4/bin
fish_add_path -g /opt/homebrew/opt/libpq/bin
fish_add_path -g /opt/homebrew/sbin
fish_add_path -g /opt/homebrew/bin

# --- Environment ---
set -x DO_NOT_TRACK 1
set -x NEXT_TELEMETRY_DISABLED 1
set -x NO_UPDATE_NOTIFIER 1
set -x TURBO_TELEMETRY_DISABLED 1
set -x COREPACK_ENABLE_UPDATE_NOTIFIER 0
set -x PNPM_CONFIG_UPDATE_NOTIFIER false
set -x PRISMA_HIDE_UPDATE_MESSAGE 1

set -x DOCKER_BUILDKIT 1
set -x DOCKER_HOST unix://$HOME/.colima/default/docker.sock
set -x HOMEBREW_NO_AUTO_UPDATE 1
set -x PYTHONDONTWRITEBYTECODE 1
set -x PYTHONPYCACHEPREFIX /tmp/python-pycache

set -x C_INCLUDE_PATH /opt/homebrew/include
set -x CPLUS_INCLUDE_PATH /opt/homebrew/include
set -x LIBRARY_PATH /opt/homebrew/lib
# set -x LDFLAGS -L/opt/homebrew/lib -L/opt/homebrew/opt/binutils/lib
# set -x CPPFLAGS -I/opt/homebrew/include -I/opt/homebrew/opt/binutils/include

set -x AWS_PROFILE default
set -x FZF_DEFAULT_COMMAND "fd --type file --color=always"
set -x FZF_DEFAULT_OPTS "--ansi"
source /opt/homebrew/opt/fzf/shell/key-bindings.fish

fish_config theme choose catppuccin-macchiato

if status is-interactive; and command -q tabs
	tabs -4
end

if test -f ~/.config/fish/config.local.fish
	source ~/.config/fish/config.local.fish
end

# --- Aliases ---
alias ls='eza --group-directories-first'
alias ll='eza --all --long --group-directories-first'
alias ta='tmux new-session -A -s main'
alias dfree='docker rmi -f $(docker images -q) && docker system prune -a -f'
alias dcu='docker compose up -d'
alias dcd='docker compose down'
alias dcdv='docker compose down --volumes'
alias repo-open='gh repo view --web'
alias pr-open='gh pr view --web'
alias pr-checkout='gh pr checkout'

# --- Functions ---

function reload --no-scope-shadowing --description 'Reload Fish configuration'
	source ~/.config/fish/config.fish
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

# --- Prompt ---
starship init fish | source
