# Codex in Docker

`codex-dkr` runs Codex in a persistent Docker container per directory, inside the existing Colima VM. A shared auth gateway injects the current host ChatGPT access token. Agents get unrestricted internet and the project directory, but no host credentials or Docker socket.

## Run

Sign in to Codex on the host with `codex login` if needed. With Colima running, use Fish:

```fish
cd ~/Code/my-project
codex-dkr
codex-dkr exec 'Implement the task and run its tests.'
codex-dkr resume --last
```

The Fish function is installed through this repository's linked Fish configuration. Docker Compose builds and starts the containers automatically. Codex runs with approval prompts and its inner filesystem sandbox disabled; Docker provides the filesystem boundary. It has passwordless sudo inside the agent container.

## Authentication

At each launch, `sync-auth.py` reads `~/.codex/auth.json` on the host and copies only the access token and account ID through stdin into the `codex-dkr-auth` Docker volume. It supports an existing ChatGPT login stored in that file. API-key and Keychain-only logins are not configured by this launcher. The host's refresh token is not copied or modified.

Only the gateway mounts that volume, read-only. It forwards Responses, compaction, and model-list requests to the fixed ChatGPT Codex endpoint. It ignores caller-supplied authentication, does not follow redirects, and suppresses upstream error bodies. There is no published host port. Agents can use the shared account through the gateway but cannot read its token through the provided API.

The gateway does not refresh OAuth tokens. If its token expires, let the host Codex refresh its login, then run `codex-dkr` again to synchronize the current token. That updates authentication for all project containers. A long-running task can fail with HTTP 401 at token expiry. A revoked host login requires `codex login` on the host again; individual project containers never require their own login.

## Files and sessions

The current directory is mounted at `/workspace`. Each project's `/home/node` is stored in its own Compose volume, so Codex sessions under `/home/node/.codex` survive restarts and container recreation. Sessions are not shared between project directories; authentication is shared. Launch `resume` from the same host directory as the original session.

Files already in the mounted project, including `.env` files, are accessible. Internet access is direct; reachable host network services remain reachable. Linked Git worktrees whose metadata lives outside the directory need a standalone clone. Keep the launcher and Compose files trusted; an agent working on this dotfiles repository can edit tooling used by later host invocations.

## Manage

Find project containers and volumes with `docker --context colima ps -a` and `docker --context colima volume ls`. The project name is `codex-dkr-` plus a hash of its absolute directory path. Use ordinary Docker commands to stop a container or open a shell. System packages persist in the container; removing a home volume deletes its saved sessions.

Gateway tests:

```sh
node --test codex-sandbox/auth/gateway.test.mjs
```

The provider configuration uses Codex's documented [custom provider settings](https://developers.openai.com/codex/config-reference).
