.PHONY: prepare deploy launchd macos-defaults

prepare:
	uvx ruff format .
	pnpm dlx prettier --write --log-level warn .

deploy:
	@git config --local filter.codex-config.clean '"$(CURDIR)/scripts/git-diff-codex-config.py"'
	@git config --local filter.codex-config.smudge cat
	@git config --local filter.codex-config.required true
	dotter deploy --force --noconfirm --verbose

launchd: # install and reload managed launchd jobs
	./scripts/launchd-hourly-snapshot.py
	./scripts/launchd-key-remapping.py

macos-defaults: # apply managed macOS preferences
	defaults write com.apple.CrashReporter DialogType -string server
