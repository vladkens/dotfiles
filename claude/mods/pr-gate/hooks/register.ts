import type { EngineInterface, Register } from "claude-code"

// A cheap, loose prefilter: pr-gate.py parses the command and decides.
const PUSH = /\bpush\b/

const PATH = {
  type: "string",
  description: "The repository's directory, absolute; the working directory when left out",
}

const OWNER = {
  type: "object",
  properties: {
    target: { type: "string", description: "A PR number or a branch name" },
    path: PATH,
  },
  required: ["target"],
}

const TOOLS = [
  {
    name: "review",
    description:
      "Review this branch's code changes since its last review with Codex: a `git push` of the" +
      " branch is denied until they pass. Takes up to 15 minutes; the answer says what to do" +
      " next (push, handle the findings, or tell the person). `accept` rejects the open findings" +
      " without changing code, one reason per finding (`<finding>: <why it is wrong>`).",
    inputSchema: {
      type: "object",
      properties: {
        accept: { type: "array", items: { type: "string" }, description: "One reason per finding" },
        path: PATH,
      },
    },
    isDeferred: false,
  },
  {
    name: "claim",
    description:
      "Make this session the owner of a PR's CI: its turn doesn't end while that CI runs, and it" +
      " hears once when CI fails. A push makes the session the owner already; claim takes over" +
      " a PR another session pushed.",
    inputSchema: OWNER,
  },
  {
    name: "release",
    description:
      "Stop watching a PR's CI: nobody owns it any more, so no turn waits for it. For CI that" +
      " can't finish.",
    inputSchema: OWNER,
    isDeferred: false,
  },
  {
    name: "status",
    description:
      "List the branches this session owns with their PR and CI state; with `all`, every owner" +
      " in the repository.",
    inputSchema: {
      type: "object",
      properties: {
        all: { type: "boolean", description: "Every owner in the repository" },
        path: PATH,
      },
    },
  },
]

function script($: EngineInterface, args: string[]) {
  return ["uv", "run", "--script", `${$.plugin.root}/pr-gate.py`, ...args]
}

// The hook commands fail open: anything but exit 2 lets the call or the stop go on.
async function hook($: EngineInterface, name: string, input: object) {
  const init = { stdin: JSON.stringify(input), timeoutMs: 30_000 }
  const run = await $.process.run(script($, [name]), init)
  if (run.stderr.trim()) $.ui.log(run.stderr.trim(), { to: "debug" })

  return run.exitCode === 2 ? run.stdout.trim() : ""
}

async function where($: EngineInterface, e: Record<string, unknown>) {
  const cwd = await $.session.cwd()
  const path = typeof e.path === "string" ? e.path.trim() : ""

  return {
    cwd: !path ? cwd : path.startsWith("/") ? path : `${cwd}/${path}`,
    env: { CLAUDE_CODE_SESSION_ID: await $.session.id() },
  }
}

function answer(code: number | null, text: string) {
  const out = text.trim() || `pr-gate exited with ${code}`

  return code === 0 ? { result: out } : { deny: out }
}

async function command($: EngineInterface, e: Record<string, unknown>, args: string[]) {
  try {
    const run = await $.process.run(script($, args), { ...(await where($, e)), timeoutMs: 120_000 })

    return answer(run.exitCode, [run.stdout, run.stderr].filter(x => x.trim()).join("\n"))
  } catch (err) {
    return { deny: `pr-gate couldn't run: ${err}` }
  }
}

async function owner($: EngineInterface, e: Record<string, unknown>, name: string) {
  const target = typeof e.target === "string" ? e.target.trim() : String(e.target ?? "")
  if (!target) return { deny: `pr-gate: ${name} needs a target, a PR number or a branch` }

  return command($, e, [name, target])
}

export const register: Register = on => {
  on("session.start", async ($, e, next) => {
    for (const tool of TOOLS) await $.tool.register(tool)

    return next(e)
  })

  on("tool.check", { tool: /^mcp__pr-gate__/ }, () => ({ decision: "allow" }))

  on("tool.call", { tool: "Bash", command: PUSH }, async ($, e, next) => {
    if (e.tool !== "Bash") return next(e)

    let input: { command: string; cwd: string; session_id: string } | undefined
    try {
      input = { command: e.command, cwd: await $.session.cwd(), session_id: await $.session.id() }
      const deny = await hook($, "pre", { command: input.command, cwd: input.cwd })
      if (deny) return { deny }
    } catch (err) {
      $.ui.log(`pr-gate: pre hook failed, not blocking: ${err}`, { to: "debug" })
    }

    const ran = await next(e)
    if (!input || ran.deny !== undefined || ran.isError) return ran

    try {
      await hook($, "post", { ...input, stdout: ran.result.stdout, stderr: ran.result.stderr })
    } catch (err) {
      $.ui.log(`pr-gate: post hook failed, not recording: ${err}`, { to: "debug" })
    }

    return ran
  })

  on("classic.Stop", async ($, e, next) => {
    const below = await next(e)
    try {
      const block = await hook($, "stop", { session_id: e.session_id })
      if (block) return { ...below, block: below.block ? `${below.block}\n\n${block}` : block }
    } catch (err) {
      $.ui.log(`pr-gate: stop hook failed, not blocking: ${err}`, { to: "debug" })
    }

    return below
  })

  // A review runs longer than the ten minutes `$.process.run` allows: spawn it.
  on("tool.call", { tool: "mcp__pr-gate__review" }, async ($, e) => {
    const accept = Array.isArray(e.accept) ? e.accept.map(String) : []
    let text = ""
    try {
      const child = $.process.spawn({
        argv: script($, ["review", ...accept.map(x => `--accept=${x}`)]),
        ...(await where($, e)),
      })
      for await (const { stream, text: piece } of child) {
        text += piece
        const line = piece.trim().split("\n").at(-1)
        if (stream === "stderr" && line) $.ui.status(line)
      }

      return answer((await child.result).code, text)
    } catch (err) {
      return { deny: `pr-gate couldn't run: ${err}\n${text}`.trim() }
    } finally {
      $.ui.status(undefined)
    }
  })

  on("tool.call", { tool: "mcp__pr-gate__claim" }, async ($, e) => owner($, e, "claim"))

  on("tool.call", { tool: "mcp__pr-gate__release" }, async ($, e) => owner($, e, "release"))

  on("tool.call", { tool: "mcp__pr-gate__status" }, async ($, e) =>
    command($, e, e.all === true ? ["status", "--all"] : ["status"]),
  )
}
