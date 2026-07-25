function git-commit-at
	GIT_AUTHOR_DATE=$argv[1] GIT_COMMITTER_DATE=$argv[1] git commit -m $argv[2]
end
