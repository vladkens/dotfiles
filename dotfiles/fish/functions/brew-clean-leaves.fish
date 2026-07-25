function brew-clean-leaves
	brew leaves \
		| fzf --multi --layout=reverse --preview 'brew info {}' \
		| xargs brew uninstall \
		&& brew autoremove
end
