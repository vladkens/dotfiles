fish_add_path -g /opt/homebrew/opt/rustup/bin

set -gx PNPM_HOME $HOME/Library/pnpm
# Include tool directories even before the first installation creates them.
for tool_bin in $HOME/.local/bin $HOME/.cargo/bin "$PNPM_HOME/bin"
	if not contains -- "$tool_bin" $PATH
		set -gx PATH "$tool_bin" $PATH
	end
end

set -gx DO_NOT_TRACK 1
set -gx NEXT_TELEMETRY_DISABLED 1
set -gx NO_UPDATE_NOTIFIER 1
set -gx TURBO_TELEMETRY_DISABLED 1
set -gx COREPACK_ENABLE_UPDATE_NOTIFIER 0
set -gx PNPM_CONFIG_UPDATE_NOTIFIER false
set -gx PRISMA_HIDE_UPDATE_MESSAGE 1
set -gx PYTHONDONTWRITEBYTECODE 1
set -gx UV_PREVIEW_FEATURES python-install-default
set -gx PYTHONPYCACHEPREFIX /tmp/python-pycache
