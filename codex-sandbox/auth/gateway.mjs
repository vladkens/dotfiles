import http from 'node:http';
import https from 'node:https';
import { readFile } from 'node:fs/promises';

const routes = new Map([
  ['/responses', 'POST'],
  ['/responses/compact', 'POST'],
  ['/models', 'GET'],
]);

export function createGateway({ tokenFile = '/auth/credentials.json', request = https.request } = {}) {
  return http.createServer(async (req, res) => {
    const fail = (status, message) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ type: 'error', error: { type: 'api_error', message } }));
    };
    // Accept only origin-form API routes. Never resolve a caller-supplied URL.
    const path = req.url.split('?')[0];
    if (routes.get(path) !== req.method) return fail(403, 'API route not allowed');

    let auth;
    try {
      auth = JSON.parse(await readFile(tokenFile, 'utf8'));
      if (!auth.access_token || /\s/.test(auth.access_token)) throw new Error('Invalid token');
    } catch {
      return fail(503, 'Run codex-dkr on the host to load Codex authentication');
    }
    const headers = {
      authorization: `Bearer ${auth.access_token}`,
      'content-type': 'application/json',
      'chatgpt-account-id': auth.account_id,
    };
    for (const name of ['user-agent', 'originator', 'session_id', 'openai-beta', 'x-codex-turn-state', 'x-codex-turn-metadata']) {
      if (req.headers[name]) headers[name] = req.headers[name];
    }
    const upstream = request({
      hostname: 'chatgpt.com', port: 443, method: req.method,
      path: `/backend-api/codex${req.url}`, headers,
    }, (response) => {
      // Never follow redirects or relay error bodies/headers that could echo credentials.
      if (response.statusCode >= 300) {
        response.resume();
        return fail(response.statusCode < 400 ? 502 : response.statusCode,
          `Codex API returned HTTP ${response.statusCode}`);
      }
      res.writeHead(response.statusCode, {
        'content-type': response.headers['content-type'] || 'application/json',
      });
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.setTimeout(300_000, () => upstream.destroy());
    upstream.on('error', () => {
      if (!res.headersSent) fail(502, 'Codex API connection failed');
      else res.destroy();
    });
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  createGateway().listen(8080, '0.0.0.0');
}
