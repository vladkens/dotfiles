set -g fish_greeting
set -gx LANG en_US.UTF-8

if test -f ~/.config/fish/config.local.fish
	source ~/.config/fish/config.local.fish
end
