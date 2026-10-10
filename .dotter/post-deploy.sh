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

# Link each shared skill into each agent's own skills directory, leaving other skills untracked.
skills_src="{{dotter.current_dir}}/agents/skills"
for skills_dir in "${HOME}/.agents/skills" "${HOME}/.claude/skills"; do
    # Older deploys linked the whole directory.
    if [ -L "$skills_dir" ]; then
        rm "$skills_dir"
    fi
    mkdir -p "$skills_dir"
    for link in "$skills_dir"/*; do
        case "$(readlink "$link" || true)" in
            "$skills_src"/*) [ -e "$link" ] || rm "$link" ;;
        esac
    done
    for skill in "$skills_src"/*/; do
        ln -sfn "${skill%/}" "$skills_dir/$(basename "$skill")"
    done
done

codex plugin marketplace add "{{dotter.current_dir}}/codex/marketplace"
codex plugin add codex-tools@dotfiles
{{/if}}
