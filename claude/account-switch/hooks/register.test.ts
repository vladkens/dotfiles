import { expect, mock, test } from "claude-code/testing"

const limits = [{ kind: "five_hour", percentUsed: 97.5, resetsAt: "2026-10-18T15:00:00Z" }]

function ran(stdout: string, exitCode = 0) {
  return {
    value: { exitCode, stdout, stderr: "", isStdoutTruncated: false, isStderrTruncated: false },
  }
}

test("hands the rate limits to the script and toasts its answer", async ($, on) => {
  const runs: { argv: readonly string[]; stdin?: string }[] = []
  const toasts: string[] = []
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("process.run", (_, e) => {
    runs.push({ argv: e.argv, stdin: e.init?.stdin })
    return ran("Claude account: sw → personal\n")
  })
  on("ui.toast", (_, e) => (toasts.push(e.text), { value: undefined }))

  await $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["rateLimits"],
  })

  expect(runs).toHaveLength(1)
  expect(runs[0]?.argv.slice(0, 3)).toEqual(["uv", "run", "--script"])
  expect(runs[0]?.argv.at(-1)).toBe("measure")
  expect(JSON.parse(runs[0]?.stdin ?? "")).toEqual(limits)
  expect(toasts).toEqual(["Claude account: sw → personal"])
})

test("skips a measurement that did not move the rate limits", async ($, on) => {
  let runs = 0
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("process.run", () => (runs++, ran("")))

  await $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["context"],
  })

  expect(runs).toBe(0)
})

test("checks initial usage and skips unchanged readings after acknowledgement", async ($, on) => {
  const clock = mock.clock(on)
  const stdins: string[] = []
  let percentUsed = 80
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.usage", () => ({
    value: {
      startedAt: 0,
      context: { window: 200_000 },
      rateLimits: [{ kind: "five_hour", percentUsed }],
    },
  }))
  on("process.run", (_, e) => (stdins.push(e.init?.stdin ?? ""), ran("")))

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  await clock.advance(60_000)
  expect(stdins).toHaveLength(1)

  percentUsed = 91
  await clock.advance(60_000)
  await clock.advance(60_000)
  expect(stdins.map(stdin => JSON.parse(stdin)[0].percentUsed)).toEqual([80, 91])
})

test("retries a skipped reading without another response or percentage change", async ($, on) => {
  const clock = mock.clock(on)
  let runs = 0
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.usage", () => ({
    value: { startedAt: 0, context: { window: 200_000 }, rateLimits: limits },
  }))
  on("process.run", () => ran("", ++runs < 3 ? 75 : 0))

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  expect(runs).toBe(1)
  await clock.advance(60_000)
  expect(runs).toBe(2)
  await clock.advance(60_000)
  expect(runs).toBe(3)
  await clock.advance(60_000)
  expect(runs).toBe(3)
})

test("retries a failed process on the timer", async ($, on) => {
  const clock = mock.clock(on)
  let runs = 0
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.usage", () => ({
    value: { startedAt: 0, context: { window: 200_000 }, rateLimits: limits },
  }))
  on("ui.toast", () => ({ value: undefined }))
  on("process.run", () => {
    if (++runs === 1) throw new Error("process unavailable")

    return ran("")
  })

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  await clock.advance(60_000)
  expect(runs).toBe(2)
})

test("keeps a switch notification and checks the new login on the next tick", async ($, on) => {
  const clock = mock.clock(on)
  const toasts: string[] = []
  let runs = 0
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.usage", () => ({
    value: { startedAt: 0, context: { window: 200_000 }, rateLimits: limits },
  }))
  on("process.run", () => (++runs === 1 ? ran("Claude account: sw → personal", 75) : ran("")))
  on("ui.toast", (_, e) => (toasts.push(e.text), { value: undefined }))

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  await clock.advance(60_000)
  expect(runs).toBe(2)
  expect(toasts).toEqual(["Claude account: sw → personal"])
})

test("does not discard a status event with unchanged percentages", async ($, on) => {
  let runs = 0
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("process.run", () => (runs++, ran("")))

  for (let i = 0; i < 2; i++) {
    await $.session.measure({
      context: { window: 200_000 },
      rateLimits: limits,
      changed: ["rateLimits"],
    })
  }

  expect(runs).toBe(2)
})

test("notices reset changes even when percentages stay the same", async ($, on) => {
  const clock = mock.clock(on)
  let resetsAt = "2099-01-01T00:00:00Z"
  let runs = 0
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.usage", () => ({
    value: {
      startedAt: 0,
      context: { window: 200_000 },
      rateLimits: [{ kind: "five_hour", percentUsed: 100, resetsAt }],
    },
  }))
  on("process.run", () => (runs++, ran("")))

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  resetsAt = "2099-01-02T00:00:00Z"
  await clock.advance(60_000)
  expect(runs).toBe(2)
})

test("keeps a measurement received while the previous check is running", async ($, on) => {
  const clock = mock.clock(on)
  let currentLimits = [] as typeof limits
  let runs = 0
  let release!: (result: ReturnType<typeof ran>) => void
  let entered!: () => void
  const started = new Promise<void>(resolve => {
    entered = resolve
  })
  const blocked = new Promise<ReturnType<typeof ran>>(resolve => {
    release = resolve
  })
  on("session.start", (_, e) => ({ cwd: e.cwd }))
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("session.usage", () => ({
    value: { startedAt: 0, context: { window: 200_000 }, rateLimits: currentLimits },
  }))
  on("process.run", () => {
    if (++runs === 1) {
      entered()
      return blocked
    }

    return ran("")
  })

  await $.session.start({ cwd: "/", surface: null, isInteractive: false })
  currentLimits = limits
  const first = $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["rateLimits"],
  })
  await started
  await $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["rateLimits"],
  })
  release(ran(""))
  await first
  await clock.advance(60_000)
  expect(runs).toBe(2)
})
