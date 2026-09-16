import dns from "node:dns/promises"
import http from "node:http"
import https from "node:https"
import net from "node:net"
import { readFile } from "node:fs/promises"
import { domainToASCII } from "node:url"

const CLAUDE_ROUTES = new Map([
  ["/v1/messages", "POST"],
  ["/v1/messages/count_tokens", "POST"],
  ["/v1/models", "GET"],
])
const CODEX_ROUTES = new Map([
  ["/responses", "POST"],
  ["/responses/compact", "POST"],
  ["/models", "GET"],
])
const ALLOWED_PORTS = new Set([80, 443])

const blockedAddresses = new net.BlockList()
for (const [address, prefix] of [
  ["0.0.0.0", 8],
  ["10.0.0.0", 8],
  ["100.64.0.0", 10],
  ["127.0.0.0", 8],
  ["169.254.0.0", 16],
  ["172.16.0.0", 12],
  ["192.0.0.0", 24],
  ["192.0.2.0", 24],
  ["192.168.0.0", 16],
  ["198.18.0.0", 15],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
  ["224.0.0.0", 4],
  ["240.0.0.0", 4],
]) {
  blockedAddresses.addSubnet(address, prefix, "ipv4")
}
for (const [address, prefix] of [
  ["::", 128],
  ["::1", 128],
  ["100::", 64],
  ["2001:db8::", 32],
  ["fc00::", 7],
  ["fe80::", 10],
  ["ff00::", 8],
]) {
  blockedAddresses.addSubnet(address, prefix, "ipv6")
}

function failJson(response, status, message) {
  response.writeHead(status, { "content-type": "application/json" })
  response.end(JSON.stringify({ type: "error", error: { type: "api_error", message } }))
}

export function createProviderGateway({
  routes,
  loadCredentials,
  upstream,
  buildHeaders,
  request = https.request,
}) {
  return http.createServer(async (incoming, outgoing) => {
    const path = (incoming.url || "").split("?")[0]
    if (routes.get(path) !== incoming.method) {
      failJson(outgoing, 403, "API route not allowed")
      return
    }

    let credentials
    try {
      credentials = await loadCredentials()
    } catch (error) {
      failJson(outgoing, 503, error.message)
      return
    }

    const requestOptions = {
      hostname: upstream.hostname,
      port: 443,
      method: incoming.method,
      path: `${upstream.pathPrefix}${incoming.url}`,
      headers: buildHeaders(credentials, incoming.headers),
    }
    const forwarded = request(requestOptions, response => {
      if (response.statusCode >= 300) {
        response.resume()
        failJson(
          outgoing,
          response.statusCode < 400 ? 502 : response.statusCode,
          `${upstream.name} API returned HTTP ${response.statusCode}`,
        )
        return
      }
      outgoing.writeHead(response.statusCode, {
        "content-type": response.headers["content-type"] || "application/json",
      })
      response.on("error", () => outgoing.destroy())
      response.pipe(outgoing)
    })
    forwarded.setTimeout(300_000, () => forwarded.destroy())
    forwarded.on("error", () => {
      if (!outgoing.headersSent) failJson(outgoing, 502, `${upstream.name} API connection failed`)
      else outgoing.destroy()
    })
    incoming.on("aborted", () => forwarded.destroy())
    outgoing.on("close", () => forwarded.destroy())
    incoming.pipe(forwarded)
  })
}

function normalizeHostname(hostname) {
  const withoutTrailingDot = hostname.endsWith(".") ? hostname.slice(0, -1) : hostname
  const normalized = domainToASCII(withoutTrailingDot).toLowerCase()
  if (!normalized || net.isIP(normalized) || normalized.includes("\0")) return null
  return normalized
}

function hostMatches(hostname, pattern) {
  if (pattern.startsWith("*.")) {
    const suffix = pattern.slice(1)
    return hostname.endsWith(suffix) && hostname.length > suffix.length
  }
  return hostname === pattern
}

function parseAuthority(authority, defaultPort) {
  try {
    const url = new URL(`http://${authority}`)
    if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) return null
    const hostname = normalizeHostname(url.hostname)
    const port = Number(url.port || defaultPort)
    if (!hostname || !Number.isInteger(port) || !ALLOWED_PORTS.has(port)) return null
    return { hostname, port }
  } catch {
    return null
  }
}

async function resolvePublicAddress(hostname, lookup = dns.lookup) {
  const addresses = await lookup(hostname, { all: true, verbatim: true })
  if (!addresses.length) throw new Error("hostname did not resolve")
  for (const { address, family } of addresses) {
    const type = family === 6 ? "ipv6" : "ipv4"
    if (blockedAddresses.check(address, type))
      throw new Error("hostname resolved to a private address")
  }
  return addresses[0]
}

function socketError(socket, status, message) {
  const body = `${message}\n`
  socket.end(
    `HTTP/1.1 ${status} ${status === 403 ? "Forbidden" : "Bad Gateway"}\r\n` +
      "Content-Type: text/plain; charset=utf-8\r\n" +
      `Content-Length: ${Buffer.byteLength(body)}\r\n` +
      "Connection: close\r\n\r\n" +
      body,
  )
}

export function createEgressProxy({ allowedHosts, lookup = dns.lookup, connect = net.connect }) {
  const patterns = allowedHosts.map(host => {
    const wildcard = host.startsWith("*.")
    const normalized = normalizeHostname(wildcard ? host.slice(2) : host)
    if (!normalized) throw new Error(`Invalid allowed hostname: ${host}`)
    return wildcard ? `*.${normalized}` : normalized
  })
  const allowed = hostname => patterns.some(pattern => hostMatches(hostname, pattern))

  const server = http.createServer(async (incoming, outgoing) => {
    let url
    try {
      url = new URL(incoming.url)
    } catch {
      failJson(outgoing, 400, "Absolute HTTP proxy URL required")
      return
    }
    if (url.protocol !== "http:") {
      failJson(outgoing, 403, "Only HTTP and HTTPS proxy traffic is supported")
      return
    }
    const target = parseAuthority(url.host, 80)
    if (!target || !allowed(target.hostname)) {
      console.error(`Network access denied: ${url.hostname || incoming.url}`)
      failJson(outgoing, 403, `Network access denied: ${url.hostname || "invalid host"}`)
      return
    }

    try {
      const address = await resolvePublicAddress(target.hostname, lookup)
      const headers = { ...incoming.headers, host: url.host }
      delete headers.authorization
      delete headers.cookie
      delete headers["proxy-authorization"]
      const forwarded = http.request(
        {
          host: address.address,
          family: address.family,
          port: target.port,
          method: incoming.method,
          path: `${url.pathname}${url.search}`,
          headers,
        },
        response => {
          outgoing.writeHead(response.statusCode, response.headers)
          response.pipe(outgoing)
        },
      )
      forwarded.on("error", () => {
        if (!outgoing.headersSent) failJson(outgoing, 502, "Public service connection failed")
        else outgoing.destroy()
      })
      incoming.pipe(forwarded)
    } catch (error) {
      console.error(`Network access denied: ${target.hostname} (${error.message})`)
      failJson(outgoing, 403, `Network access denied: ${target.hostname}`)
    }
  })

  server.on("connect", async (incoming, client, head) => {
    const target = parseAuthority(incoming.url, 443)
    if (!target || !allowed(target.hostname)) {
      const hostname = target?.hostname || incoming.url
      console.error(`Network access denied: ${hostname}`)
      socketError(client, 403, `Network access denied: ${hostname}`)
      return
    }

    try {
      const address = await resolvePublicAddress(target.hostname, lookup)
      const upstream = connect({
        host: address.address,
        family: address.family,
        port: target.port,
      })
      upstream.once("connect", () => {
        client.write("HTTP/1.1 200 Connection Established\r\n\r\n")
        if (head.length) upstream.write(head)
        upstream.pipe(client)
        client.pipe(upstream)
      })
      upstream.on("error", () => socketError(client, 502, "Public service connection failed"))
      client.on("error", () => upstream.destroy())
    } catch (error) {
      console.error(`Network access denied: ${target.hostname} (${error.message})`)
      socketError(client, 403, `Network access denied: ${target.hostname}`)
    }
  })

  return server
}

async function loadClaudeCredentials(path = "/auth/claude-token") {
  const token = (await readFile(path, "utf8")).trim()
  if (!token || /\s/.test(token))
    throw new Error("Configure Claude authentication with agent-box auth claude")
  return { token }
}

async function loadCodexCredentials(path = "/auth/codex.json") {
  const credentials = JSON.parse(await readFile(path, "utf8"))
  if (!credentials.access_token || /\s/.test(credentials.access_token) || !credentials.account_id) {
    throw new Error("Invalid Codex credentials")
  }
  return credentials
}

export function createClaudeGateway(options = {}) {
  return createProviderGateway({
    routes: CLAUDE_ROUTES,
    loadCredentials: options.loadCredentials || (() => loadClaudeCredentials(options.tokenFile)),
    upstream: { name: "Claude", hostname: "api.anthropic.com", pathPrefix: "" },
    buildHeaders: ({ token }, headers) => ({
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "anthropic-version": headers["anthropic-version"] || "2023-06-01",
      "anthropic-beta": [
        ...new Set([
          ...(headers["anthropic-beta"] || "").split(",").filter(Boolean),
          "oauth-2025-04-20",
        ]),
      ].join(","),
      ...Object.fromEntries(
        ["user-agent", "x-app"].filter(name => headers[name]).map(name => [name, headers[name]]),
      ),
    }),
    request: options.request,
  })
}

export function createCodexGateway(options = {}) {
  return createProviderGateway({
    routes: CODEX_ROUTES,
    loadCredentials: options.loadCredentials || (() => loadCodexCredentials(options.tokenFile)),
    upstream: { name: "Codex", hostname: "chatgpt.com", pathPrefix: "/backend-api/codex" },
    buildHeaders: ({ access_token: token, account_id: accountId }, headers) => ({
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "chatgpt-account-id": accountId,
      ...Object.fromEntries(
        [
          "user-agent",
          "originator",
          "session_id",
          "openai-beta",
          "x-codex-turn-state",
          "x-codex-turn-metadata",
        ]
          .filter(name => headers[name])
          .map(name => [name, headers[name]]),
      ),
    }),
    request: options.request,
  })
}

function listen(server, port) {
  server.listen(port, "0.0.0.0", () => console.log(`Listening on ${port}`))
}

if (import.meta.url === `file://${process.argv[1]}`) {
  let allowedHosts
  try {
    allowedHosts = JSON.parse(process.env.SANDBOX_ALLOWED_HOSTS || "[]")
    if (!Array.isArray(allowedHosts) || allowedHosts.some(host => typeof host !== "string")) {
      throw new Error("expected an array of hostnames")
    }
  } catch (error) {
    throw new Error(`Invalid SANDBOX_ALLOWED_HOSTS: ${error.message}`)
  }
  listen(createClaudeGateway(), 8081)
  listen(createCodexGateway(), 8082)
  listen(createEgressProxy({ allowedHosts }), 3128)
}
