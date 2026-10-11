function claude-qh --description 'Start Claude Code with the QH work account'
	command env CLAUDE_CONFIG_DIR="$HOME/.claude-qh" claude $argv
end
