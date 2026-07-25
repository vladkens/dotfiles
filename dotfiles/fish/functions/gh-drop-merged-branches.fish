function gh-drop-merged-branches
	set current_branch (git branch --show-current)

	for branch in (git branch --format='%(refname:short)')
		if contains -- "$branch" "$current_branch" main master develop
			continue
		end

		set pr (gh pr list --state merged --head "$branch" --json number,url --jq '.[0] | select(. != null) | "\(.number)\t\(.url)"')

		if test -n "$pr"
			set pr_number (string split \t -- "$pr")[1]
			set pr_url (string split \t -- "$pr")[2]

			if contains -- --apply $argv
				echo "Deleting $branch (#$pr_number) $pr_url"
				git branch -D "$branch"
			else
				echo "Would delete $branch (#$pr_number) $pr_url"
			end
		end
	end
end
