#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

git config --local filter.codex-config.clean scripts/git-diff-codex-config.py
git config --local filter.codex-config.smudge cat
git config --local filter.codex-config.required true
