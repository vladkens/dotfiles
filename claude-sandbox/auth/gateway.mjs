import http from 'node:http';
import https from 'node:https';
import { readFile } from 'node:fs/promises';

const routes = new Map([
  ['/v1/messages', 'POST'],
  ['/v1/messages/count_tokens', 'POST'],
  ['/v1/models', 'GET'],
]);

export function createGateway({ tokenFile = '/auth/token', request = https.request } = {}) {
  return http.createServer(async (req, res) => {
    const fail = (status, message) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ type: 'error', error: { type: 'api_error', message } }));
    };
    // Accept only origin-form API routes. Never resolve a caller-supplied URL.
    const path = req.url.split('?')[0];
    if (routes.get(path) !== req.method) return fail(403, 'API route not allowed');

    let token;
    try {
      token = (await readFile(tokenFile, 'utf8')).trim();
      if (!token || /\s/.test(token)) throw new Error('Invalid token');
    } catch {
      return fail(503, 'Configure the Claude token on the host with set-token.py');
    }

    const headers = {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      'anthropic-version': req.headers['anthropic-version'] || '2023-06-01',
      'anthropic-beta': [...new Set([
        ...(req.headers['anthropic-beta'] || '').split(',').filter(Boolean),
        'oauth-2025-04-20',
      ])].join(','),
    };
    for (const name of ['user-agent', 'x-app']) {
      if (req.headers[name]) headers[name] = req.headers[name];
    }
    const upstream = request({
      hostname: 'api.anthropic.com', port: 443, method: req.method,
      path: req.url, headers,
    }, (response) => {
      // Never follow redirects or relay error bodies/headers that could echo credentials.
      if (response.statusCode >= 300) {
        response.resume();
        return fail(response.statusCode < 400 ? 502 : response.statusCode,
          `Claude API returned HTTP ${response.statusCode}`);
      }
      res.writeHead(response.statusCode, {
        'content-type': response.headers['content-type'] || 'application/json',
      });
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.setTimeout(300_000, () => upstream.destroy());
    upstream.on('error', () => {
      if (!res.headersSent) fail(502, 'Claude API connection failed');
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
