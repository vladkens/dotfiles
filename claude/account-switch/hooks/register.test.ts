import { expect, test } from "claude-code/testing"

const limits = [{ kind: "five_hour", percentUsed: 97.5, resetsAt: "2026-10-18T15:00:00Z" }]

test("hands the rate limits to the script and toasts its answer", async ($, on) => {
  const runs: { argv: readonly string[]; stdin?: string }[] = []
  const toasts: string[] = []
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("process.run", (_, e) => {
    runs.push({ argv: e.argv, stdin: e.init?.stdin })
    return { value: { exitCode: 0, stdout: "Claude account: sw → personal\n", stderr: "" } }
  })
  on("ui.toast", (_, e) => (toasts.push(e.text), { value: undefined }))

  await $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["rateLimits"],
  })

  expect(runs).toHaveLength(1)
  expect(runs[0].argv.slice(0, 3)).toEqual(["uv", "run", "--script"])
  expect(runs[0].argv.at(-1)).toBe("measure")
  expect(JSON.parse(runs[0].stdin ?? "")).toEqual(limits)
  expect(toasts).toEqual(["Claude account: sw → personal"])
})

test("skips a measurement that did not move the rate limits", async ($, on) => {
  let runs = 0
  on("session.measure", (_, e) => ({ changed: e.changed }))
  on("process.run", () => (runs++, { value: { exitCode: 0, stdout: "", stderr: "" } }))

  await $.session.measure({
    context: { window: 200_000 },
    rateLimits: limits,
    changed: ["context"],
  })

  expect(runs).toBe(0)
})
