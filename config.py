#!/usr/bin/python3
# The system Python, because a fresh computer has no uv yet.

from pathlib import Path

from dotsync.engine import (
    AppleAgent,
    Default,
    Hotkey,
    LaunchAgent,
    LaunchDaemon,
    Module,
    Profile,
    run,
)

# MARK: Command line

cli = Module(
    "cli",
    brew=[
        *["curl", "coreutils", "less", "git", "git-lfs", "jq", "ripgrep"],
        *["fish", "starship", "bat", "eza", "fd", "fzf"],
    ],
    files={
        "dotfiles/git": "~/.config/git",
        "dotfiles/fish/config.fish": "~/.config/fish/config.fish",
        "dotfiles/fish/conf.d/terminal.fish": "~/.config/fish/conf.d/terminal.fish",
        "dotfiles/fish/functions": "~/.config/fish/functions",
        "dotfiles/starship/starship.toml": "~/.config/starship.toml",
        "dotfiles/bat/config": "~/.config/bat/config",
    },
)

vim = Module(
    "vim",
    brew=["vim"],
    files={"dotfiles/vim": "~/.config/vim"},
)

tmux = Module(
    "tmux",
    brew=["tmux"],
    files={"dotfiles/tmux/tmux.conf": "~/.config/tmux/tmux.conf"},
)

scripts = Module(
    "scripts",
    brew=["uv", "gh", "oxipng", "pngquant"],
    files={"bin/*": "~/.local/bin"},
    needs=[cli],
)

# MARK: Terminal and editors

fonts = Module(
    "fonts",
    cask=["font-jetbrains-mono"],
)

ghostty = Module(
    "ghostty",
    cask=["ghostty"],
    files={"dotfiles/ghostty": "~/.config/ghostty"},
    needs=[cli, fonts],
)

zed = Module(
    "zed",
    cask=["zed"],
    files={"dotfiles/zed/*": "~/.config/zed"},
    needs=[cli, fonts],
)

sublime = Module(
    "sublime",
    cask=["sublime-text"],
    files={"dotfiles/sublime/*": "~/Library/Application Support/Sublime Text/Packages/User"},
)

wezterm = Module(
    "wezterm",
    cask=["wezterm"],
    files={"dotfiles/wezterm": "~/.config/wezterm"},
    needs=[fonts],
)

revdiff = Module(
    "revdiff",
    brew=["umputun/apps/revdiff"],
    files={"dotfiles/revdiff/config": "~/.config/revdiff/config"},
    needs=[cli],
)

# MARK: Development

develop = Module(
    "develop",
    brew=["rustup", "sccache", "uv", "pnpm", "gh"],
    cargo=["cargo-edit"],
    files={
        "dotfiles/fish/conf.d/develop.fish": "~/.config/fish/conf.d/develop.fish",
        "dotfiles/cargo/config.toml": "~/.cargo/config.toml",
    },
    needs=[cli],
    setup="""
        export PNPM_HOME="${PNPM_HOME:-$HOME/Library/pnpm}"
        export PATH="$HOME/.local/bin:$PNPM_HOME/bin:$PATH"
        rustup default stable
        rustup component add rust-src
        rustup toolchain install nightly --profile minimal --component rustfmt
        uv python install --default
        pnpm runtime set node lts -g
        # pnpm may copy Homebrew's relative symlink into its global bin directory.
        if [ -L "$PNPM_HOME/bin/node" ] && [ ! -e "$PNPM_HOME/bin/node" ]; then
            ln -sf "$(command -v pnpm)" "$PNPM_HOME/bin/node"
        fi
    """,
    setup_check="""
        export RUSTUP_AUTO_INSTALL=0
        rustup default | grep -q '^stable-' &&
        rustup component list --installed --toolchain stable | grep -qx rust-src &&
        rustup component list --installed --toolchain nightly | grep -q '^rustfmt-' &&
        uv python find --managed-python &&
        "${PNPM_HOME:-$HOME/Library/pnpm}/bin/node" --version | grep -q '^v'
    """,
)

sublime_merge = Module(
    "sublime-merge",
    cask=["sublime-merge"],
    files={"dotfiles/sublime-merge/*": "~/Library/Application Support/Sublime Merge/Packages/User"},
    needs=[zed, fonts],
)

containers = Module(
    "containers",
    brew=["docker", "docker-compose", "docker-buildx", "colima"],
    files={"dotfiles/fish/conf.d/containers.fish": "~/.config/fish/conf.d/containers.fish"},
    needs=[cli],
    setup="""
        plugins="${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins"
        mkdir -p "$plugins"
        for plugin in docker-compose docker-buildx; do
            ln -sfn "$(brew --prefix)/lib/docker/cli-plugins/$plugin" "$plugins/$plugin"
        done
    """,
    setup_check="docker compose version && docker buildx version",
)

mise = Module(
    "mise",
    brew=["mise"],
    files={"dotfiles/mise": "~/.config/mise"},
)

npm = Module(
    "npm",
    files={"dotfiles/npmrc": "~/.npmrc"},
    needs=[develop],
)

terraform = Module(
    "terraform",
    brew=["hashicorp/tap/terraform"],
    files={"dotfiles/terraformrc": "~/.terraformrc"},
    setup='mkdir -p "$HOME/.terraform.d/plugin-cache"',
    setup_check='test -d "$HOME/.terraform.d/plugin-cache"',
)

# MARK: Agents

agent_tools = Module(
    "agent-tools",
    brew=["actionlint", "asciinema"],
    cargo=["unjar"],
    needs=[develop],
)

claude = Module(
    "claude",
    cask=["claude-code"],
    files={
        "claude/settings.json": "~/.claude/settings.json",
        "claude/statusline.sh": "~/.claude/statusline.sh",
        "claude/keybindings.json": "~/.claude/keybindings.json",
        "agents/agents.md": "~/.claude/CLAUDE.md",
        "agents/skills/*": "~/.claude/skills",
        "claude/mods/*": "~/.claude/skills",
    },
    needs=[cli, scripts, agent_tools],
)

codex = Module(
    "codex",
    cask=["codex"],
    files={
        "codex/config.toml": "~/.codex/config.toml",
        "codex/rules": "~/.codex/rules",
        "codex/hooks.json": "~/.codex/hooks.json",
        "codex/hooks": "~/.codex/hooks",
        "agents/agents.md": "~/.codex/AGENTS.md",
        "agents/skills/*": "~/.agents/skills",
    },
    needs=[cli, scripts, agent_tools],
)

# MARK: macOS

# fmt: off
MACOS_DEFAULTS = [
    Default("com.apple.HIToolbox", "AppleFnUsageType", 0, logout=True),  # Keyboard: Globe key does nothing
    Default("-g", "com.apple.keyboard.fnState", True, activate=True),  # Keyboard: F1, F2 as standard keys
    Default("-g", "AppleWindowTabbingMode", "always"),  # Desktop & Dock: always prefer tabs
    Default("-g", "AppleInterfaceStyleSwitchesAutomatically", True, logout=True),  # Appearance: auto light/dark
    Default("-g", "NSMenuEnableActionImages", False),  # Menus: hide item icons
    Default("-g", "com.apple.sound.uiaudio.enabled", False),  # Sound: no UI sound effects
    Default("-g", "TISRomanSwitchState", 0),  # Keyboard: Caps Lock doesn't switch ABC
    Default("-g", "TSMLanguageIndicatorEnabled", False),  # Keyboard: no input source popup
    Default("-g", "NSAutomaticQuoteSubstitutionEnabled", False),  # Keyboard: no smart quotes
    Default("-g", "NSAutomaticDashSubstitutionEnabled", False),  # Keyboard: no smart dashes
    Default("-g", "NSAutomaticCapitalizationEnabled", False),  # Keyboard: no auto-capitalization
    Default("-g", "NSAutomaticPeriodSubstitutionEnabled", False),  # Keyboard: no period on double-space
    Default("-g", "ApplePressAndHoldEnabled", False),  # Keyboard: hold repeats key, no accents
    Default("-g", "InitialKeyRepeat", 25, logout=True),  # Keyboard: delay until repeat (short)
    Default("-g", "AppleActionOnDoubleClick", "Maximize"),  # Desktop & Dock: title bar double-click zooms
    Default("-g", "AppleShowScrollBars", "WhenScrolling"),  # Appearance: scroll bars when scrolling
    Default("-g", "AppleICUForce24HourTime", True, logout=True),  # Date & Time: 24-hour time
    Default("com.apple.CrashReporter", "DialogType", "server"),  # Crash reports: no dialogs
    Default("com.apple.dock", "tilesize", 56),  # Dock: icon size
    Default("com.apple.dock", "size-immutable", True),  # Dock: lock icon size
    Default("com.apple.dock", "show-recents", False),  # Dock: don't show recent apps
    Default("com.apple.dock", "wvous-br-corner", 1),  # Hot Corners: bottom-right does nothing
    Default("com.apple.dock", "wvous-br-modifier", 0),  # Hot Corners: bottom-right without modifier
    Default("com.apple.dock", "minimize-to-application", True),  # Dock: minimize windows into app icon
    Default("com.apple.finder", "NewWindowTarget", "PfHm"),  # Finder: new windows open Home
    Default("com.apple.finder", "NewWindowTargetPath", f"file://{Path.home()}/"),  # Finder: new windows' Home path
    Default("com.apple.finder", "FXPreferredViewStyle", "Nlsv"),  # Finder: list view by default
    Default("com.apple.finder", "ShowRecentTags", False),  # Finder sidebar: hide recent tags
    Default("com.apple.finder", "SidebarDevicesSectionDisclosedState", False),  # Finder sidebar: collapse Locations
    Default("com.apple.finder", "_FXSortFoldersFirst", True),  # Finder: keep folders on top
    Default("com.apple.finder", "ShowPathbar", True),  # Finder: show path bar at the bottom
    Default("com.apple.finder", "FXDefaultSearchScope", "SCcf"),  # Finder: search the current folder
    Default("com.apple.finder", "FXEnableExtensionChangeWarning", False),  # Finder: no extension change warning
    Default("com.apple.menuextra.clock", "ShowSeconds", True),  # Menu bar clock: show seconds
    Default("com.apple.menuextra.clock", "ShowDate", 2),  # Menu bar clock: hide date
    Default("com.apple.menuextra.clock", "ShowDayOfWeek", False),  # Menu bar clock: hide day of week
    Default("com.apple.WindowManager", "EnableTiledWindowMargins", False),  # Desktop & Dock: no tiled window margins
    Hotkey(60, [32, 49, 262144]),  # Shortcuts: Ctrl+Space previous input source
    Hotkey(61, [65535, 80, 0]),  # Shortcuts: F19 next input source
]
# fmt: on

# https://developer.apple.com/library/archive/technotes/tn2450/_index.html
CAPS_LOCK_TO_F19 = [
    "/usr/bin/hidutil",
    "property",
    "--set",
    {
        "UserKeyMapping": [
            {
                "HIDKeyboardModifierMappingSrc": 0x700000039,
                "HIDKeyboardModifierMappingDst": 0x70000006E,
            }
        ]
    },
]

MACOS_LAUNCHD = [
    # Keyboard: Caps Lock acts as F19
    LaunchAgent("com.local.KeyRemapping", CAPS_LOCK_TO_F19),
    # Time Machine: hourly local snapshots
    LaunchDaemon("local.hourly-snapshot", ["/usr/bin/tmutil", "localsnapshot"], hourly=True),
    # Media keys: Play/Pause reach Chrome and other apps
    AppleAgent("com.apple.rcd"),
]

macos = Module(
    "macos",
    defaults=MACOS_DEFAULTS,
    launchd=MACOS_LAUNCHD,
)

# desktop = Module(
#     "desktop",
#     cask=["telegram", "shottr", "keepingyouawake", "itsycal", "discord"],
# )

pro_m2 = Module(
    "pro-m2",
    files={"dotfiles/fish/conf.d/pro-m2.fish": "~/.config/fish/conf.d/pro-m2.fish"},
    needs=[cli],
)

# MARK: Profiles

air = Profile(
    "air",
    [
        cli,
        vim,
        tmux,
        scripts,
        ghostty,
        zed,
        develop,
        sublime_merge,
        claude,
        codex,
        macos,
    ],
)

pro = Profile(
    "pro",
    [
        cli,
        vim,
        tmux,
        scripts,
        ghostty,
        zed,
        develop,
        sublime_merge,
        claude,
        codex,
        macos,
        containers,
        mise,
        npm,
        terraform,
        sublime,
        wezterm,
        pro_m2,
    ],
)

# MARK: Run

if __name__ == "__main__":
    run(air, pro)
