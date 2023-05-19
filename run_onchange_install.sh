#/usr/bin/env sh

brew install ssh git
brew install exa bat fd watchexec
brew install asdf
brew install fish fisher fzf starship
brew install docker docker-compose colima act
brew install awscli kubectx
brew install mongosh mongodb-database-tools
brew install libpq

# brew install --cask karabiner-elements
# brew install --cask visual-studio-code
# brew install --cask iterm2

brew tap homebrew/cask-fonts
brew install --cask font-jetbrains-mono
# brew install --cask font-jetbrains-mono-nerd-font

asdf plugin add nodejs
asdf plugin add python

asdf install nodejs 18.16.0
asdf install python 3.11.3
