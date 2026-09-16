import assert from "node:assert/strict"
import { PassThrough } from "node:stream"
import net from "node:net"
import { test } from "node:test"
import { createClaudeGateway, createCodexGateway, createEgressProxy } from "./gateway.mjs"

function fakeRequest(calls) {
  return (options, callback) => {
    calls.push(options)
    const request = new PassThrough()
    request.setTimeout = () => {}
    request.resume()
    request.on("finish", () => {
      const response = new PassThrough()
      response.statusCode = 200
      response.headers = {
        "content-type": "text/event-stream",
        location: "https://evil.example",
        "set-cookie": "secret",
      }
      callback(response)
      response.end("data: complete\n\n")
    })
    return request
  }
}

async function listen(server) {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
  return `http://127.0.0.1:${server.address().port}`
}

async function close(server) {
  await new Promise(resolve => server.close(resolve))
}

test("Claude gateway injects its token and rejects unapproved routes", async () => {
  const calls = []
  const server = createClaudeGateway({
    loadCredentials: async () => ({ token: "claude-secret" }),
    request: fakeRequest(calls),
  })
  const base = await listen(server)
  try {
    const response = await fetch(`${base}/v1/messages`, {
      method: "POST",
      headers: { authorization: "attacker", "anthropic-beta": "existing-beta" },
      body: "{}",
    })
    assert.equal(await response.text(), "data: complete\n\n")
    assert.equal(response.headers.get("set-cookie"), null)
    assert.equal(response.headers.get("location"), null)
    assert.equal(calls[0].hostname, "api.anthropic.com")
    assert.equal(calls[0].headers.authorization, "Bearer claude-secret")
    assert.match(calls[0].headers["anthropic-beta"], /oauth-2025-04-20/)
    assert.equal((await fetch(`${base}/oauth/token`, { method: "POST" })).status, 403)
  } finally {
    await close(server)
  }
})

test("Codex gateway injects its token and account ID", async () => {
  const calls = []
  const server = createCodexGateway({
    loadCredentials: async () => ({ access_token: "codex-secret", account_id: "account" }),
    request: fakeRequest(calls),
  })
  const base = await listen(server)
  try {
    const response = await fetch(`${base}/responses`, {
      method: "POST",
      headers: { authorization: "attacker", "chatgpt-account-id": "attacker" },
      body: "{}",
    })
    assert.equal(response.status, 200)
    assert.equal(calls[0].hostname, "chatgpt.com")
    assert.equal(calls[0].path, "/backend-api/codex/responses")
    assert.equal(calls[0].headers.authorization, "Bearer codex-secret")
    assert.equal(calls[0].headers["chatgpt-account-id"], "account")
  } finally {
    await close(server)
  }
})

function connectThroughProxy(port, authority) {
  return new Promise((resolve, reject) => {
    const socket = net.connect(port, "127.0.0.1")
    let response = ""
    socket.setEncoding("utf8")
    socket.on("connect", () => {
      socket.write(`CONNECT ${authority} HTTP/1.1\r\nHost: ${authority}\r\n\r\n`)
    })
    socket.on("data", chunk => {
      response += chunk
      if (response.includes("\r\n\r\n")) {
        socket.destroy()
        resolve(response)
      }
    })
    socket.on("error", reject)
  })
}

test("egress proxy allows configured hosts and blocks everything else", async () => {
  const connections = []
  const server = createEgressProxy({
    allowedHosts: ["registry.npmjs.org", "*.githubusercontent.com"],
    lookup: async () => [{ address: "8.8.8.8", family: 4 }],
    connect: options => {
      connections.push(options)
      const stream = new PassThrough()
      queueMicrotask(() => stream.emit("connect"))
      return stream
    },
  })
  await listen(server)
  try {
    const allowed = await connectThroughProxy(server.address().port, "registry.npmjs.org:443")
    assert.match(allowed, /^HTTP\/1.1 200/)
    assert.equal(connections.length, 1)
    assert.equal(connections[0].host, "8.8.8.8")

    const wildcard = await connectThroughProxy(
      server.address().port,
      "raw.githubusercontent.com:443",
    )
    assert.match(wildcard, /^HTTP\/1.1 200/)
    assert.equal(connections.length, 2)

    const denied = await connectThroughProxy(server.address().port, "example.com:443")
    assert.match(denied, /^HTTP\/1.1 403/)
    assert.equal(connections.length, 2)
  } finally {
    await close(server)
  }
})

test("egress proxy rejects allowed hostnames that resolve privately", async () => {
  const server = createEgressProxy({
    allowedHosts: ["registry.npmjs.org"],
    lookup: async () => [{ address: "127.0.0.1", family: 4 }],
    connect: () => assert.fail("private address must not be connected"),
  })
  await listen(server)
  try {
    const response = await connectThroughProxy(server.address().port, "registry.npmjs.org:443")
    assert.match(response, /^HTTP\/1.1 403/)
  } finally {
    await close(server)
  }
})
