fish_add_path -g $HOME/Library/Android/sdk/emulator
fish_add_path -g /opt/homebrew/opt/mysql-client@8.4/bin
fish_add_path -g /opt/homebrew/opt/libpq/bin

set -gx C_INCLUDE_PATH /opt/homebrew/include
set -gx CPLUS_INCLUDE_PATH /opt/homebrew/include
set -gx LIBRARY_PATH /opt/homebrew/lib
set -gx AWS_PROFILE default
