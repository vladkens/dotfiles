#!/bin/sh
set -eu

mkdir -p "${HOME}/.terraform.d/plugin-cache"

codex plugin marketplace add "{{dotter.current_dir}}/codex/marketplace"
codex plugin add codex-tools@dotfiles
