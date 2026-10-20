import type { EngineInterface, Register, SessionRateLimit } from "claude-code"

// Readings only wake a verified check. Keep work pending until Python acknowledges it.
let last = "[]"
let pending = false
let running = false

function key(limits: readonly SessionRateLimit[]) {
  return JSON.stringify(limits.map(limit => [limit.kind, limit.percentUsed, limit.resetsAt]))
}

async function check($: EngineInterface, limits: readonly SessionRateLimit[], changed = false) {
  const reading = key(limits)
  if (changed || reading !== last) pending = true

  last = reading
  if (!pending || running) return

  running = true
  pending = false
  try {
    const script = `${$.plugin.root}/account-switch.py`
    const run = await $.process.run(["uv", "run", "--script", script, "measure"], {
      stdin: JSON.stringify(limits),
      timeoutMs: 60_000,
    })
    if (run.exitCode !== 0) pending = true

    const text = (run.stdout || run.stderr).trim()
    if (text) $.ui.toast(text)
  } catch {
    pending = true
    $.ui.toast("Account usage check could not run; will retry")
  } finally {
    running = false
  }
}

export const register: Register = on => {
  on("session.measure", async ($, e, next) => {
    const result = await next(e)
    if (e.changed.includes("rateLimits")) await check($, e.rateLimits, true)

    return result
  })

  // Retry skipped checks even if a blocked session produces no more responses.
  on("session.start", async ($, e, next) => {
    const result = await next(e)
    $.clock.every(60_000, async () => check($, (await $.session.usage()).rateLimits))
    await check($, (await $.session.usage()).rateLimits)

    return result
  })
}
