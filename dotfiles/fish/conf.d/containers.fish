set -gx DOCKER_BUILDKIT 1
set -gx DOCKER_HOST unix://$HOME/.colima/default/docker.sock

if status is-interactive
	alias dfree='docker rmi -f $(docker images -q) && docker system prune -a -f'
	alias dcu='docker compose up -d'
	alias dcd='docker compose down'
	alias dcdv='docker compose down --volumes'

	function colima-up --description 'Start Colima (creating the VM if needed) with 4 CPUs, 8 GiB and Rosetta'
		colima start --cpus 4 --memory 8 --disk 100 --vm-type vz --vz-rosetta --mount-type virtiofs $argv
	end
end
