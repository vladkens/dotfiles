if status is-interactive
    # Commands to run in interactive sessions can go here
end

set -x LANG en_US.UTF-8
set -x HOMEBREW_NO_AUTO_UPDATE 0
set -x DOCKER_HOST unix:///Users/user/.colima/default/docker.sock
fish_add_path ~/.local/bin

starship init fish | source
source /opt/homebrew/opt/asdf/libexec/asdf.fish

alias ls='exa --group-directories-first'
alias ll='exa --all --long --grid --group-directories-first'
