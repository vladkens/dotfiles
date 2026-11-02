.PHONY: prepare plan apply test
$(shell scripts/git-setup.sh)

prepare:
	uvx ruff format .
	pnpm dlx prettier --write --log-level warn .

plan: # show what apply would change
	./config.py

apply: # apply the plan on this machine
	./config.py apply

test:
	/usr/bin/python3 dotsync/test_engine.py
	uv run --script claude/mods/account-switch/test-account-switch.py
	uv run --script claude/mods/pr-gate/test-pr-gate.py
	claude plugin test claude/mods/account-switch
	claude plugin test claude/mods/pr-gate
