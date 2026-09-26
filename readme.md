# dotfiles

Personal application configs and agent settings, managed with Dotter.

## Setup

Install Homebrew, clone this repository, then install Dotter:

```sh
brew install dotter
```

Create `.dotter/local.toml` (ignored by Git) to select a profile:

```toml
packages = ["air-m5"]
```

- `air-m5`: `terminal` and `develop`.
- `pro-m2`: both groups plus the remaining previous configuration.

`develop` installs rustup, uv, and pnpm, configures Fish paths, and installs
Rust stable, the default stable Python supplied by uv, and Node.js LTS.

Preview config changes, then install the selected groups and link their configs:

```sh
dotter deploy --dry-run
make deploy
```

`make deploy` can overwrite existing target files (`--force`).

## Files

- `.dotter/global.toml`: profiles, groups, and config destinations.
- `.dotter/*.Brewfile`: programs to install for each group.
- `dotfiles/`: application configs.
- `claude/`, `codex/`: agent settings and extensions.
- `bin/`: personal CLI tools; `scripts/`: repository utilities.

## Codex Config Notes

Opened issues:

- https://github.com/openai/codex/issues/32647
- https://github.com/openai/codex/issues/32648
- https://github.com/openai/codex/issues/32658

### Network

`network.enabled = false`: commands have no network access. Commands matched by `prefix_rule(..., decision="allow")` are the exception: they bypass the sandbox and have network access (probably filesystem too, since this is a sandbox bypass).

`network.enabled = true`: network access is enabled for all commands.

There is also an option to restrict traffic by domains. It requires all three: `network.enabled = true`, `network.mode = "limited"`, and `features.network_proxy = true`. Then traffic is filtered by `network.domains`. Current caveat: even `prefix_rule(... allow)` commands are routed through the proxy, so an allowlisted command fails if its domain is not allowed there.

Note: `network.mode = "limited"` is silently ineffective without `features.network_proxy = true`.

### Filesystem

Denied reads under `[permissions.<profile>.filesystem.":workspace_roots"]` disable the unsandboxed part of `rules.allow`:

```toml
[permissions.dev_workspace.filesystem.":workspace_roots"]
"**/*.env" = "deny"
```

With any filesystem `deny`, Codex does not run allowlisted commands outside the sandbox. The rule still matches, and the approval prompt can be skipped, but execution stays sandboxed because denied reads only work inside the sandbox.

Practical result: `rules.allow` stops being useful as a sandbox bypass. Commands that need denied files, such as `.env`, fail even when the command is allowlisted.
