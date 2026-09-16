function codex-anal --description 'Create an analysis workspace and start Codex'
	if test (count $argv) -ne 1
		echo 'usage: codex-anal <name>' >&2
		return 2
	end

	set -l name $argv[1]
	if not string match -rq '^[a-z0-9]+(-[a-z0-9]+)*$' -- "$name"
		echo 'codex-anal: name must use lowercase kebab-case' >&2
		return 2
	end

	if not command -q codex
		echo 'codex-anal: codex command not found' >&2
		return 127
	end

	set -l dir "$HOME/Code/anal/$name"
	if test -e "$dir"
		echo "codex-anal: $dir already exists" >&2
		return 1
	end

	command mkdir -- "$dir"; or return 1
	cd -- "$dir"; or return 1
	command codex -C "$dir"
end
