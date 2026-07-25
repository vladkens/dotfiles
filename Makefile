DOTDROP := dotdrop --no-banner --cfg=$(CURDIR)/config.yaml
DOTDROP_PROFILE := --profile=default

.PHONY: sync

sync: # Create or restore managed links.
	$(DOTDROP) install $(DOTDROP_PROFILE)
