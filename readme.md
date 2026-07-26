# dotfiles

Configurations are grouped by application under `dotfiles/`. [Dotdrop](https://github.com/deadc0de6/dotdrop) maps them to their real paths using `config.yaml`.

## Usage

Install Dotdrop using the package manager available on the current operating system, then create or restore the configured links:

```sh
make sync
```

After linking, changes made through application UIs modify the repository files directly and appear in `git diff`.

## Why Dotdrop

[GNU Stow](https://www.gnu.org/software/stow/) mirrors target paths inside every package and creates symlinks. It is simple, but forces the repository to reproduce the `$HOME` hierarchy and has no per-file destination map.

[Dotter](https://github.com/SuperCuber/dotter) provides explicit mappings, symlinks, and rendered copies. It is a good simple linker, but lacks Dotdrop's target-to-repository update workflow and is maintained conservatively as feature-complete.

[chezmoi](https://www.chezmoi.io/) is mature and powerful, but its encoded source tree and templating model are more complex than needed here. [yadm](https://yadm.io/) makes UI edits natural by using `$HOME` as a Git work tree, but the repository still mirrors home paths instead of grouping files by application.

[Dotdrop](https://dotdrop.readthedocs.io/) was selected because it keeps an explicit `src`/`dst` map, supports both copies and links, allows a clean application-oriented repository layout, and can synchronize detached changes back into the repository.

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
