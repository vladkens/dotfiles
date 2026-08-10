DOTDROP := dotdrop --no-banner --cfg=$(CURDIR)/dotdrop.yaml
DOTDROP_PROFILE := --profile=default

.PHONY: prepare sync launchd

prepare: # default command
	uvx ruff format .
	pnpm dlx prettier --write --log-level warn .

sync: # create or restore managed links
	git config --local filter.codex-config.clean '"$(CURDIR)/scripts/git-diff-codex-config.py"'
	git config --local filter.codex-config.smudge cat
	git config --local filter.codex-config.required true
	$(DOTDROP) install --force-actions $(DOTDROP_PROFILE)

launchd: # install and reload managed launchd jobs
	./scripts/launchd-hourly-snapshot.py
	./scripts/launchd-key-remapping.py
