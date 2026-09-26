#!/bin/sh
set -eu

git config --local filter.codex-config.clean '"{{dotter.current_dir}}/scripts/git-diff-codex-config.py"'
git config --local filter.codex-config.smudge cat
git config --local filter.codex-config.required true

{{#if dotter.packages.terminal}}
brew bundle install --file="{{dotter.current_dir}}/.dotter/terminal.Brewfile" --no-upgrade
{{/if}}

{{#if dotter.packages.develop}}
brew bundle install --file="{{dotter.current_dir}}/.dotter/develop.Brewfile" --no-upgrade
{{/if}}
