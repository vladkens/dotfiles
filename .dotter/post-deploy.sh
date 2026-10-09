#!/bin/sh
set -eu

uv run --script "{{dotter.current_dir}}/scripts/prune-dotfile-links.py"

make -C "{{dotter.current_dir}}" macos-defaults

{{#if dotter.packages.containers}}
docker_plugins="${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins"
mkdir -p "$docker_plugins"
ln -sfn "$(brew --prefix)/lib/docker/cli-plugins/docker-compose" "$docker_plugins/docker-compose"
ln -sfn "$(brew --prefix)/lib/docker/cli-plugins/docker-buildx" "$docker_plugins/docker-buildx"
{{/if}}

{{#if dotter.packages.develop}}
export PNPM_HOME="${PNPM_HOME:-$HOME/Library/pnpm}"
export PATH="$(brew --prefix rustup)/bin:$HOME/.local/bin:$PNPM_HOME/bin:$PATH"

rustup default stable
uv python install --default
pnpm runtime set node lts -g
# pnpm may copy Homebrew's relative symlink into its global bin directory.
if [ -L "$PNPM_HOME/bin/node" ] && [ ! -e "$PNPM_HOME/bin/node" ]; then
    ln -sf "$(command -v pnpm)" "$PNPM_HOME/bin/node"
fi
{{/if}}

{{#if dotter.packages.pro-m2}}
mkdir -p "${HOME}/.terraform.d/plugin-cache"

codex plugin marketplace add "{{dotter.current_dir}}/codex/marketplace"
codex plugin add codex-tools@dotfiles
{{/if}}
