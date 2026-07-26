DOTDROP := dotdrop --no-banner --cfg=$(CURDIR)/config.yaml
DOTDROP_PROFILE := --profile=default

.PHONY: prepare sync

prepare:
	uvx ruff format .
	npx prettier --write --log-level warn .

sync: # Create or restore managed links.
	$(DOTDROP) install $(DOTDROP_PROFILE)
