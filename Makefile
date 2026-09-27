.PHONY: prepare deploy launchd macos-defaults

prepare:
	uvx ruff format .
	pnpm dlx prettier --write --log-level warn .

deploy:
	./scripts/deploy.sh

launchd: # install and reload managed launchd jobs
	./scripts/launchd-hourly-snapshot.py
	./scripts/launchd-key-remapping.py

macos-defaults: # apply managed macOS preferences
	defaults write com.apple.CrashReporter DialogType -string server
	defaults write -g NSMenuEnableActionImages -bool NO
