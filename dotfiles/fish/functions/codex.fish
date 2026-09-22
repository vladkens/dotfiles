function codex --description 'Start Codex with a random pet'
	set -l pet_root "$HOME/.codex/pets"
	if set -q CODEX_HOME; and test -n "$CODEX_HOME"
		set pet_root "$CODEX_HOME/pets"
	end

	set -l manifests
	for pet_dir in $pet_root/*/
		if test -f "$pet_dir/pet.json"
			set -a manifests "$pet_dir/pet.json"
		end
	end

	set -l pets
	if test (count $manifests) -gt 0
		for manifest in (jq -r 'select(.spriteVersionNumber == null or .spriteVersionNumber == 1) | input_filename' $manifests)
			set -a pets "custom:"(path basename (path dirname "$manifest"))
		end
	end

	if test (count $pets) -gt 0
		set -l pet (random choice $pets)
		command codex -c "tui.pet=\"$pet\"" $argv
	else
		command codex $argv
	end
end
