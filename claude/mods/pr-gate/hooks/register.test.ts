import { expect, test } from "claude-code/testing"
import type { On } from "claude-code"

type Run = { argv: readonly string[]; stdin?: string; cwd?: string; env?: Record<string, string> }

const PASSED = "pr-gate: passed (quick review found nothing). Push again."
const PUSHED = "To github.com:vladkens/x.git\n   1111111..2222222  feat -> feat\n"

function ran(stdout: string, exitCode = 0, stderr = "") {
  return {
    value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false },
  }
}

function session(on: On) {
  on("session.id", () => ({ value: "s1" }))
  on("session.cwd", () => ({ value: "/repo" }))
  on("ui.log", () => ({ value: undefined }))
}

// The script's answer by subcommand; every call lands in runs.
function script(on: On, answers: Record<string, ReturnType<typeof ran>>) {
  const runs: Run[] = []
  on("process.run", (_, e) => {
    runs.push({ argv: e.argv, stdin: e.init?.stdin, cwd: e.init?.cwd, env: e.init?.env })
    return answers[e.argv[4] ?? ""] ?? ran("")
  })

  return runs
}

function bash(on: On, result: object) {
  const commands: string[] = []
  on("tool.call", { tool: "Bash" }, (_, e) => {
    if (e.tool === "Bash") commands.push(e.command)
    return result as never
  })

  return commands
}

test("denies an unreviewed push without running it", async ($, on) => {
  session(on)
  const runs = script(on, { pre: ran("pr-gate: this push needs a review first.\n", 2) })
  const commands = bash(on, { result: { stdout: "", stderr: PUSHED, interrupted: false } })

  const res = await $.tool.call({ tool: "Bash", command: "git push -u origin feat" })

  expect(res.deny ?? res.text).toContain("needs a review first")
  expect(commands).toEqual([])
  expect(runs.map(x => x.argv.at(-1))).toEqual(["pre"])
  expect(runs[0]?.argv.slice(0, 3)).toEqual(["uv", "run", "--script"])
  expect(JSON.parse(runs[0]?.stdin ?? "")).toEqual({
    command: "git push -u origin feat",
    cwd: "/repo",
  })
})

test("lets a reviewed push run, then records who pushed it", async ($, on) => {
  session(on)
  const runs = script(on, {})
  const commands = bash(on, { result: { stdout: "", stderr: PUSHED, interrupted: false } })

  const res = await $.tool.call({ tool: "Bash", command: "git -C sub push" })

  expect(res.deny).toBeUndefined()
  expect(commands).toEqual(["git -C sub push"])
  expect(runs.map(x => x.argv.at(-1))).toEqual(["pre", "post"])
  expect(JSON.parse(runs[1]?.stdin ?? "")).toEqual({
    command: "git -C sub push",
    cwd: "/repo",
    session_id: "s1",
    stdout: "",
    stderr: PUSHED,
  })
})

test("records nothing after a push that failed", async ($, on) => {
  session(on)
  const runs = script(on, {})
  bash(on, { isError: true, result: "Exit code 1\nerror: failed to push", text: "Exit code 1" })

  const res = await $.tool.call({ tool: "Bash", command: "git push" })

  expect(res.isError).toBe(true)
  expect(runs.map(x => x.argv.at(-1))).toEqual(["pre"])
})

test("lets the push run when the gate itself fails", async ($, on) => {
  session(on)
  on("process.run", () => {
    throw new Error("uv is missing")
  })
  const commands = bash(on, { result: { stdout: "", stderr: PUSHED, interrupted: false } })

  const res = await $.tool.call({ tool: "Bash", command: "git push" })

  expect(res.deny).toBeUndefined()
  expect(commands).toEqual(["git push"])
})

test("hands any command naming push to the script, and only those", async ($, on) => {
  session(on)
  const runs = script(on, { pre: ran("pr-gate: this push needs a review first.\n", 2) })
  const commands = bash(on, { result: { stdout: "", stderr: "", interrupted: false } })

  for (const command of ["FOO=1 git push", "bash -c 'git push'", "ls"]) {
    await $.tool.call({ tool: "Bash", command })
  }

  expect(runs.map(x => JSON.parse(x.stdin ?? "").command)).toEqual([
    "FOO=1 git push",
    "bash -c 'git push'",
  ])
  expect(runs.map(x => x.argv.at(-1))).toEqual(["pre", "pre"])
  expect(commands).toEqual(["ls"])
})

test("keeps the turn going while CI runs", async ($, on) => {
  session(on)
  const runs = script(on, { stop: ran("pr-gate: CI is still running (x#1).\n", 2) })
  on("classic.Stop", () => ({}))

  const res = await $.classic.Stop({ session_id: "s1", stop_hook_active: false })

  expect(res.block).toBe("pr-gate: CI is still running (x#1).")
  expect(JSON.parse(runs[0]?.stdin ?? "")).toEqual({ session_id: "s1" })
})

test("lets the turn end when nothing is waited for", async ($, on) => {
  session(on)
  script(on, { stop: ran("") })
  on("classic.Stop", () => ({}))

  const res = await $.classic.Stop({ session_id: "s1", stop_hook_active: false })

  expect(res.block).toBeUndefined()
})

test("registers the tools and allows them", async ($, on) => {
  const names: string[] = []
  on("tool.register", (_, e) => {
    names.push(e.name)
    return { value: { tool: `mcp__pr-gate__${e.name}` } }
  })
  on("session.start", (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })

  expect(names).toEqual(["review", "claim", "release", "status"])
  const check = await $.tool.check({ tool: "mcp__pr-gate__review", input: {} })
  expect(check.decision).toBe("allow")
})

test("serves status, claim and release from the session's repository", async ($, on) => {
  session(on)
  const runs = script(on, {
    status: ran("x  feat  #1  3m ago  green\n"),
    claim: ran("pr-gate: this session owns feat (#12) now.\n"),
    release: ran("", 1, "pr-gate: nobody owns feat.\n"),
  })

  const status = await $.tool.call({ tool: "mcp__pr-gate__status", all: true })
  const claim = await $.tool.call({ tool: "mcp__pr-gate__claim", target: "12", path: "/other" })
  const release = await $.tool.call({ tool: "mcp__pr-gate__release", target: "feat" })
  const empty = await $.tool.call({ tool: "mcp__pr-gate__claim" })

  expect(status.result).toBe("x  feat  #1  3m ago  green")
  expect(claim.result).toBe("pr-gate: this session owns feat (#12) now.")
  expect(release.deny).toBe("pr-gate: nobody owns feat.")
  expect(empty.deny ?? empty.text).toContain("needs a target")
  expect(runs.map(x => x.argv.slice(4))).toEqual([
    ["status", "--all"],
    ["claim", "12"],
    ["release", "feat"],
  ])
  expect(runs.map(x => x.cwd)).toEqual(["/repo", "/other", "/repo"])
  expect(runs[0]?.env).toEqual({ CLAUDE_CODE_SESSION_ID: "s1" })
})

test("runs a review as a spawned child, its progress on the status line", async ($, on) => {
  session(on)
  const spawns: { argv: readonly string[]; cwd?: string }[] = []
  const statuses: (string | undefined)[] = []
  on("ui.status", (_, e) => (statuses.push(e.text), { value: undefined }))
  on("process.spawn", async function* (_, e) {
    spawns.push({ argv: e.argv, cwd: e.cwd })
    yield { stream: "stderr" as const, text: "pr-gate: quick review of 3 changed lines…\n" }
    yield { stream: "stdout" as const, text: "- a.py:1: wrong\n\npr-gate: findings to handle.\n" }
    return { value: { code: 1, signal: null } }
  })

  const res = await $.tool.call({
    tool: "mcp__pr-gate__review",
    accept: ["- a.py:1: wrong: it is right"],
  })

  expect(spawns[0]?.argv.slice(4)).toEqual(["review", "--accept=- a.py:1: wrong: it is right"])
  expect(spawns[0]?.cwd).toBe("/repo")
  expect(res.deny).toContain("findings to handle")
  expect(statuses).toEqual(["quick review of 3 changed lines…", undefined])
})

test("answers a passed review as the tool's result", async ($, on) => {
  session(on)
  on("ui.status", () => ({ value: undefined }))
  on("process.spawn", async function* () {
    yield { stream: "stdout" as const, text: `${PASSED}\n` }
    return { value: { code: 0, signal: null } }
  })

  const res = await $.tool.call({ tool: "mcp__pr-gate__review" })

  expect(res.result).toBe(PASSED)
})
