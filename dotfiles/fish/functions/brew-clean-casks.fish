function brew-clean-casks
	brew list --cask \
		| fzf --multi --layout=reverse --preview 'brew info --cask {}' \
		| xargs brew uninstall --cask \
		&& brew autoremove
end
