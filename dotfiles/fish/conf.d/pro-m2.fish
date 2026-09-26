fish_add_path -g $HOME/Library/Android/sdk/emulator
fish_add_path -g /opt/homebrew/opt/mysql-client@8.4/bin
fish_add_path -g /opt/homebrew/opt/libpq/bin

set -gx DOCKER_BUILDKIT 1
set -gx DOCKER_HOST unix://$HOME/.colima/default/docker.sock
set -gx C_INCLUDE_PATH /opt/homebrew/include
set -gx CPLUS_INCLUDE_PATH /opt/homebrew/include
set -gx LIBRARY_PATH /opt/homebrew/lib
set -gx AWS_PROFILE default

if status is-interactive
	alias dfree='docker rmi -f $(docker images -q) && docker system prune -a -f'
	alias dcu='docker compose up -d'
	alias dcd='docker compose down'
	alias dcdv='docker compose down --volumes'
end
