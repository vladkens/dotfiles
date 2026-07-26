import process from "node:process"

let rawInput = ""

for await (const chunk of process.stdin) {
  rawInput += chunk
}

const input = JSON.parse(rawInput)
const command = input.tool_input?.command
const home = process.env.HOME

if (input.tool_name !== "Bash" || typeof command !== "string" || !home) {
  process.exit(0)
}

const escapeRegExp = value => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
const homePrefix = `${home}/.codex/`
const commandPrefix = new RegExp(`^([\\t ]*\\S+[\\t ]+)${escapeRegExp(homePrefix)}`)
const rewrittenCommand = command.replace(commandPrefix, "$1~/.codex/")

if (rewrittenCommand === command) {
  process.exit(0)
}

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      updatedInput: {
        command: rewrittenCommand,
      },
    },
  }),
)
