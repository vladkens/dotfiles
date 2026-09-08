function claude-dkr --description 'Run Claude in Docker on Colima for the current project'
    set -l workspace (pwd -P)
    if contains -- "$workspace" / "$HOME"
        echo 'Run claude-dkr from a project directory, not your home or filesystem root.' >&2
        return 1
    end

    set -l source_dir (path resolve (path dirname (functions --details claude-dkr))/../../../claude-sandbox)
    set -l project_id (printf '%s' "$workspace" | shasum -a 256 | string sub -l 16)
    set -l container claude-dkr-proxy-$project_id
    set -l image claude-dkr:docker

    docker --context colima network inspect claude-dkr >/dev/null 2>&1
    or docker --context colima network create claude-dkr >/dev/null
    or return

    if not docker --context colima container inspect claude-dkr-auth >/dev/null 2>&1
        docker --context colima build -t claude-dkr-auth:local "$source_dir/auth"
        or return
        docker --context colima create --name claude-dkr-auth --network claude-dkr \
            --read-only --cap-drop ALL --security-opt no-new-privileges \
            --mount type=volume,source=claude-dkr-auth,target=/auth,readonly \
            claude-dkr-auth:local >/dev/null
        or return
    end
    docker --context colima start claude-dkr-auth >/dev/null
    or return
    docker --context colima exec claude-dkr-auth test -s /auth/token
    or begin
        echo "Configure Claude authentication once: python3 $source_dir/set-token.py" >&2
        return 1
    end

    if not docker --context colima container inspect "$container" >/dev/null 2>&1
        docker --context colima info >/dev/null
        or return
        if not docker --context colima image inspect "$image" >/dev/null 2>&1
            docker --context colima build -t "$image" "$source_dir"
            or return
        end
        docker --context colima create --name "$container" --init --network claude-dkr \
            --mount "type=bind,source=$workspace,target=/workspace" \
            --mount "type=volume,source=$container-home,target=/home/node" \
            "$image" >/dev/null
        or return
    end

    docker --context colima start "$container" >/dev/null
    or return
    docker --context colima exec "$container" node -e '
        const fs = require("fs");
        const path = "/home/node/.claude.json";
        const config = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, "utf8")) : {};
        config.hasCompletedOnboarding = true;
        config.projects ??= {};
        config.projects["/workspace"] ??= {};
        config.projects["/workspace"].hasTrustDialogAccepted = true;
        fs.writeFileSync(path, JSON.stringify(config), {mode: 0o600});
        fs.mkdirSync("/home/node/.claude", {recursive: true});
        const settingsPath = "/home/node/.claude/settings.json";
        const settings = fs.existsSync(settingsPath) ? JSON.parse(fs.readFileSync(settingsPath, "utf8")) : {};
        settings.skipDangerousModePermissionPrompt = true;
        fs.writeFileSync(settingsPath, JSON.stringify(settings), {mode: 0o600});
    '
    or return
    set -l interactive -i
    if isatty stdin; and isatty stdout
        set -a interactive -t
    end
    docker --context colima exec $interactive "$container" \
        env ANTHROPIC_BASE_URL=http://claude-dkr-auth:8080 CLAUDE_CODE_OAUTH_TOKEN=proxy \
        claude --dangerously-skip-permissions --disallowedTools AskUserQuestion \
        --append-system-prompt 'Work autonomously. Make reasonable decisions without asking questions. Complete the task and verify the result. If blocked, report the blocker.' $argv
end
