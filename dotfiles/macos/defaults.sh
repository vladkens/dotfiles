#!/bin/sh
set -eu

# Existing system preferences.
defaults write com.apple.CrashReporter DialogType -string server
defaults write -g NSMenuEnableActionImages -bool NO

# Enable media keys by loading the Remote Control daemon.
launchctl enable "gui/$(id -u)/com.apple.rcd"
if ! launchctl print "gui/$(id -u)/com.apple.rcd" >/dev/null 2>&1; then
    launchctl bootstrap "gui/$(id -u)" /System/Library/LaunchAgents/com.apple.rcd.plist
fi

# Disable interface sound effects, including moving files to Trash.
defaults write -g com.apple.sound.uiaudio.enabled -bool false

# scripts/launchd-key-remapping.py installs a LaunchAgent that maps Caps Lock to F19.
# These settings complete that setup: disable native Caps Lock language switching
# and bind F19 (key code 80) to "Select next source in Input menu" (hotkey 61).
# Both parts are needed for Caps Lock to switch languages through the remap.
defaults write -g TISRomanSwitchState -int 0
defaults write com.apple.symbolichotkeys AppleSymbolicHotKeys -dict-add 60 \
    '<dict><key>enabled</key><true/><key>value</key><dict><key>parameters</key><array><integer>32</integer><integer>49</integer><integer>262144</integer></array><key>type</key><string>standard</string></dict></dict>'
defaults write com.apple.symbolichotkeys AppleSymbolicHotKeys -dict-add 61 \
    '<dict><key>enabled</key><true/><key>value</key><dict><key>parameters</key><array><integer>65535</integer><integer>80</integer><integer>0</integer></array><key>type</key><string>standard</string></dict></dict>'
# Load the saved shortcuts into the current session; defaults alone only saves them.
/System/Library/PrivateFrameworks/SystemAdministration.framework/Resources/activateSettings -u

# Hide the input indicator (undocumented; behavior depends on macOS version).
defaults write -g TSMLanguageIndicatorEnabled -bool false
defaults write -g NSAutomaticQuoteSubstitutionEnabled -bool false
defaults write -g NSAutomaticDashSubstitutionEnabled -bool false

# Finder: open the home folder, use list view, and hide sidebar sections.
defaults write com.apple.finder NewWindowTarget -string PfHm
defaults write com.apple.finder NewWindowTargetPath -string "file://$HOME/"
defaults write com.apple.finder FXPreferredViewStyle -string Nlsv
defaults write com.apple.finder ShowRecentTags -bool false
defaults write com.apple.finder SidebarDevicesSectionDisclosedState -bool false

# Dock: fixed icon size; prevent resizing by dragging the separator.
defaults write com.apple.dock tilesize -int 56
defaults write com.apple.dock size-immutable -bool true

# Disable the startup chime (requires administrator privileges).
# sudo nvram StartupMute=%01

printf '%s\n' 'Preferences applied. Relaunch Finder to see the changes.'
