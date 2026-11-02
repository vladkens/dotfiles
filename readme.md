# dotfiles

My macOS configs, tools and agent settings, deployed by [config.py](config.py).

## New Mac

Install [Homebrew](https://brew.sh), then:

```sh
git clone https://github.com/vladkens/dotfiles.git ~/Code/dotfiles
cd ~/Code/dotfiles
echo <name> > .profile  # once: this Mac's profile, air or pro
make plan               # see what will change
make apply              # do it (asks "yes" first)
```

The profile is kept in the untracked `.profile`; edit it to switch.

If `apply` stops on a file that differs, `./config.py apply --force` moves the old one to `.backup/` and links the repository version.

## Adding something

Everything is listed in `config.py`: add a program or config file to the matching module (or a new module), and make sure that module is in each profile at the bottom that needs it. Then `make apply`.

## Folders

- `dotfiles/`: app configs.
- `claude/`, `codex/`, `agents/`: agent settings and skills.
- `bin/`: my CLI tools.
- `dotsync/`, `scripts/`: what makes this repository work.

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
