function codex-resume --description 'Resume the last Codex session from this shell'
	set -l session_file "$TMPDIR"codex-session-$fish_pid
	if not test -s "$session_file"
		echo 'codex-resume: no Codex session has exited in this shell' >&2
		return 1
	end

	read -l session_id < "$session_file"
	codex resume "$session_id" $argv
end
