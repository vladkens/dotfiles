#!/bin/sh
set -eu

git config --local filter.codex-config.clean '"{{dotter.current_dir}}/scripts/git-diff-codex-config.py"'
git config --local filter.codex-config.smudge cat
git config --local filter.codex-config.required true

{{#each dotter.packages}}
{{#if this}}
brewfile="{{@root.dotter.current_dir}}/.dotter/Brewfile-{{@key}}"
if [ -f "$brewfile" ]; then
    brew bundle install --file="$brewfile" --no-upgrade
fi
{{/if}}
{{/each}}
