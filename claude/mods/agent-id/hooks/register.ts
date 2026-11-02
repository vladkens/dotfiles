import type { Register } from "claude-code"

export const register: Register = on => {
  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: "agent-id",
      description: "Show the session ID and copy it to the clipboard",
    })

    return next(e)
  })

  on("command.run", { command: "agent-id" }, async $ => {
    const id = await $.session.id()
    const copied = await $.ui.copy({ text: id })

    return {
      text: copied.isCopied ? `${id} (copied)` : `${id} (not copied: ${copied.reason})`,
    }
  })
}
