import type { Register } from "claude-code"

// Hands every rate-limit reading to account-switch.py, which switches the profile's login when
// the live account's window is nearly full and another account has room, or back once it resets.
export const register: Register = on => {
  on("session.measure", async ($, e, next) => {
    const result = await next(e)
    if (!e.changed.includes("rateLimits") || e.rateLimits.length === 0) return result

    const script = `${$.plugin.root}/account-switch.py`
    const run = await $.process.run(["uv", "run", "--script", script, "measure"], {
      stdin: JSON.stringify(e.rateLimits),
      timeoutMs: 60_000,
    })
    const text = (run.exitCode === 0 ? run.stdout : run.stderr).trim()
    if (text) $.ui.toast(text)

    return result
  })
}
