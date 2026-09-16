# Agent box

`agent-box` runs Claude Code and Codex in one persistent Docker container per project. A single shared gateway keeps both account tokens outside agent containers and limits public network access to configured package and source hosts.

## Run

Start Colima, change to the project directory, and launch either agent:

```sh
agent-box claude
agent-box claude -p 'Implement the task and run its tests.'
agent-box codex
agent-box codex exec 'Implement the task and run its tests.'
agent-box codex resume --last
```

Use `agent-box shell` to open Bash in the same project container. Files and tools installed under `/home/node` survive container recreation, while Claude and Codex keep their own state in separate home directories. System packages installed outside the home volume do not survive recreation.

## Authentication

Generate a Claude setup token on the host and store it in the gateway volume:

```sh
claude setup-token
agent-box auth claude
```

Codex authentication is copied from the current host login each time Codex starts. It can also be synchronized explicitly:

```sh
codex login
agent-box auth codex
```

Only the gateway mounts the authentication volume. Agent containers receive placeholder model credentials and use internal Claude and Codex endpoints that inject the real tokens upstream.

## Network access

Agent containers join the internal `agent-box` Docker network and have no direct route to the internet. Their HTTP, HTTPS, and `ALL_PROXY` variables point to the gateway, which permits only the public hosts enabled in `config.toml`.

The default groups allow public access to GitHub, npm, crates.io, and PyPI. Add a host to an existing service or define and enable another service when a project needs it. The gateway logs denied hostnames and rejects IP literals, private addresses, and ports other than 80 and 443.

HTTPS is tunneled without interception. The gateway controls destination hostnames but does not install a custom certificate authority, inspect encrypted requests, or provide credentials to public services.

## Container lifecycle

Every invocation creates missing images, networks, volumes, and containers. A stopped project container is started automatically. Changes to the agent Dockerfile recreate project containers on their next invocation, while changes to gateway code or the network allowlist recreate the shared gateway. Persistent home and authentication volumes survive automatic recreation.

Lifecycle commands operate on the current project:

```sh
agent-box stop
agent-box recreate
agent-box remove
```

`stop` stops the container, `recreate` replaces it immediately, and `remove` removes it until the next launch. None of these commands removes its home volume.

The shared gateway uses Docker's `unless-stopped` restart policy. It is recreated automatically when its source or network configuration changes.

## Development

Run gateway tests with:

```sh
node --test agent-box/gateway/gateway.test.mjs
```
