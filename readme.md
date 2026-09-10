# dotfiles

Configuration sources are grouped by application under `dotfiles/`. Claude and Codex configuration and extensions live together under their dedicated top-level directories.

## Setup

After cloning the repository, install Dotter and deploy the configuration:

```sh
brew install dotter
make deploy
```

## Repository Layout

- Keep application configs under `dotfiles/<app>/` and preserve their directory structure.
- If an application mixes configuration with local state in the same directory, manage only the files and subdirectories that belong to the configuration.
- Keep personal CLI commands under `bin/`; Dotter installs them into `~/.local/bin`.
- Put files installed directly in `$HOME` at the root of `dotfiles/`.
- Keep Claude and Codex configuration and extensions under `claude/` and `codex/`, and keep repository tooling in `scripts/` or the repository root.

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
