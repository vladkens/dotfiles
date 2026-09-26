set -gx DOCKER_BUILDKIT 1
set -gx DOCKER_HOST unix://$HOME/.colima/default/docker.sock

if status is-interactive
	alias dfree='docker rmi -f $(docker images -q) && docker system prune -a -f'
	alias dcu='docker compose up -d'
	alias dcd='docker compose down'
	alias dcdv='docker compose down --volumes'
end
