.PHONY: prepare deploy launchd

prepare:
	uvx ruff format .
	pnpm dlx prettier --write --log-level warn .

deploy:
	./scripts/deploy.sh

launchd: # install and reload managed launchd jobs
	./scripts/launchd-hourly-snapshot.py
	./scripts/launchd-key-remapping.py
