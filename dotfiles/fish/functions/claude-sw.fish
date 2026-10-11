function claude-sw --description 'Start Claude Code with the SW work account'
	command env CLAUDE_CONFIG_DIR="$HOME/.claude-sw" claude $argv
end
