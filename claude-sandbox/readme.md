# Claude in Docker

One persistent agent container per project and one shared authentication container, all in the existing Colima VM. Agents have unrestricted outbound internet. Only Claude API calls go through the authentication container; it injects the real OAuth token without exposing it to the agent.

## Run

With Colima running, use Fish from the directory you want to share:

```fish
cd ~/Code/my-project
claude-dkr
claude-dkr -p 'Implement the task in TODO.md and run the relevant tests.'
```

The function is installed through this repository's linked Fish configuration. Images and containers are created automatically. Authentication is shared across projects and survives container restarts and recreation. No per-project login is needed.

## Authentication setup

Configure one long-lived token on the host. Generate it with the host Claude CLI, then paste it into the hidden prompt:

```sh
claude setup-token
python3 ~/Code/dotfiles/claude-sandbox/set-token.py
```

The helper writes the token through Docker stdin into the `claude-dkr-auth` volume. It is never put in command arguments, an image, the repository, or an agent volume. The auth container mounts it read-only and rereads it for each request. Repeat setup only when the token expires or is revoked, not when changing projects. No OAuth refresh token is stored or automatically refreshed.

## Access

Agents run as `node` with passwordless `sudo`, unrestricted internet, a writable project mount at `/workspace`, and a persistent home volume. They can install tools and use the network directly. No `HTTP_PROXY` or `HTTPS_PROXY` is configured. Host home directories, SSH agents, Docker sockets, and host environment credentials are not forwarded.

The launcher points Claude at `http://claude-dkr-auth:8080` using a nonsecret placeholder credential. The auth container only forwards Messages, token-counting, and model-list requests to `https://api.anthropic.com`. It ignores caller-supplied authorization and destination headers, does not follow redirects, and does not relay upstream error bodies. It has no published host port or Docker socket. Its filesystem and token volume are read-only.

Agents can consume the shared Claude account through the gateway. This separates possession of the real token from use of the account; it does not impose spending limits. Files already inside the project, including `.env` files, remain accessible. Host services reachable over the network remain reachable. This is container isolation within Colima, not protection against Docker or kernel vulnerabilities.

Tool permission prompts and `AskUserQuestion` are disabled. The launcher asks Claude to make reasonable decisions independently. Missing external inputs may still prevent completion.

## Manage

Project containers are named `claude-dkr-proxy-` followed by a hash of the project path. Find them with `docker --context colima ps -a`. Use ordinary Docker commands:

```sh
docker --context colima exec -it CONTAINER bash
docker --context colima stop CONTAINER
```

System packages persist in the container; home files persist in its `CONTAINER-home` volume. To rebuild an agent image and recreate a project's container:

```sh
docker --context colima build -t claude-dkr:docker ~/Code/dotfiles/claude-sandbox
docker --context colima rm -f CONTAINER
```

For auth gateway code changes:

```sh
docker --context colima build -t claude-dkr-auth:local ~/Code/dotfiles/claude-sandbox/auth
docker --context colima rm -f claude-dkr-auth
```

The next `claude-dkr` recreates the removed container. Removing a container does not remove its volumes. Removing `claude-dkr-auth` with `docker volume rm` deletes the shared token.

Agent containers from the earlier direct-login setup are not reused, because their home volumes may contain real credentials. Their files remain intact. Linked Git worktrees whose metadata lives outside the shared directory need a standalone clone.

Run gateway security tests with `node --test claude-sandbox/auth/gateway.test.mjs`.
