function codex --description 'Start Codex or resume this shell\'s last session with back'
	set -l session_file "$TMPDIR"codex-session-$fish_pid
	set -lx CODEX_SESSION_FILE "$session_file"

	if test "$argv[1]" = back
		if not test -s "$session_file"
			echo 'codex back: no Codex session recorded in this shell' >&2
			return 1
		end

		read -l session_id < "$session_file"
		set argv resume "$session_id" $argv[2..-1]
	end

	command codex $argv
end
