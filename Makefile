DOTDROP := dotdrop --no-banner --cfg=$(CURDIR)/config.yaml
DOTDROP_PROFILE := --profile=default

.PHONY: prepare sync

prepare:
	uvx ruff format .
	npx prettier --write --log-level warn .

sync: # Create or restore managed links.
	git config --local filter.codex-config.clean 'python3 "$(CURDIR)/scripts/git-diff-codex-config.py"'
	git config --local filter.codex-config.required true
	$(DOTDROP) install $(DOTDROP_PROFILE)
	codex plugin marketplace add "$(CURDIR)/codex-plugins"
	codex plugin add codex-tools@dotfiles
