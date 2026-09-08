function codex-dkr --description 'Run Codex in Docker on Colima for the current project'
    set -lx CODEX_WORKSPACE (pwd -P)
    if contains -- "$CODEX_WORKSPACE" / "$HOME"
        echo 'Run codex-dkr from a project directory.' >&2
        return 1
    end
    set -l source_dir (path resolve (path dirname (functions --details codex-dkr))/../../../codex-sandbox)
    set -l project_id (printf '%s' "$CODEX_WORKSPACE" | shasum -a 256 | string sub -l 16)
    set -l compose docker --context colima compose -p codex-dkr-$project_id -f "$source_dir/compose.yml"

    docker --context colima compose -p codex-dkr-auth -f "$source_dir/auth/compose.yml" up -d
    or return
    python3 "$source_dir/sync-auth.py"
    or return
    $compose up -d
    or return
    set -l terminal
    if not isatty stdin; or not isatty stdout
        set terminal -T
    end
    $compose exec $terminal agent codex --dangerously-bypass-approvals-and-sandbox \
        -c 'model_provider="gateway"' \
        -c 'model_providers.gateway={name="Codex gateway",base_url="http://codex-dkr-auth:8080",wire_api="responses",supports_websockets=false}' \
        -c 'projects."/workspace".trust_level="trusted"' \
        -c 'developer_instructions="Work autonomously. Make reasonable decisions without asking questions. Complete the task and verify the result. Report blockers."' $argv
end
