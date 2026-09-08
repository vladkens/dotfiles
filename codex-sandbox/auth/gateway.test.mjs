import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createGateway } from './gateway.mjs';

test('fixed upstream, secret injection, streaming, and rejected escape routes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'claude-gateway-'));
  const tokenFile = join(dir, 'token');
  await writeFile(tokenFile, JSON.stringify({access_token: 'test-secret', account_id: 'test-account'}));
  let calls = [];
  let status = 200;
  const server = createGateway({ tokenFile, request(options, callback) {
    calls.push(options);
    const request = new PassThrough();
    request.setTimeout = () => {};
    request.resume();
    request.on('finish', () => {
      const response = new PassThrough();
      response.statusCode = status;
      response.headers = { 'content-type': 'text/event-stream', location: 'https://evil.example', 'set-cookie': 'test-secret' };
      callback(response);
      response.write(status === 200 ? 'data: first\n\n' : 'test-secret');
      response.end(status === 200 ? 'data: second\n\n' : '');
    });
    return request;
  }});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const res = await fetch(`${base}/responses?beta=true`, { method: 'POST', headers: {
      authorization: 'attacker', 'x-api-key': 'attacker', host: 'evil.example',
      'chatgpt-account-id': 'attacker-account',
    }, body: '{}' });
    assert.equal(await res.text(), 'data: first\n\ndata: second\n\n');
    assert.equal(res.headers.get('set-cookie'), null);
    assert.equal(res.headers.get('location'), null);
    assert.equal(calls[0].hostname, 'chatgpt.com');
    assert.equal(calls[0].path, '/backend-api/codex/responses?beta=true');
    assert.equal(calls[0].headers['chatgpt-account-id'], 'test-account');
    assert.equal(calls[0].headers.authorization, 'Bearer test-secret');
    assert.equal(calls[0].headers['x-api-key'], undefined);
    assert.equal(calls[0].headers.host, undefined);
    for (const path of ['/auth/token', '//evil.example/responses', '/v1/%2e%2e/auth', '/v1/oauth/token']) {
      assert.equal((await fetch(base + path, { method: 'POST' })).status, 403);
    }
    assert.equal(calls.length, 1);
    for (status of [302, 401, 500]) {
      const error = await fetch(`${base}/responses`, { method: 'POST' });
      assert.equal(error.status, status === 302 ? 502 : status);
      assert.ok(!(await error.text()).includes('test-secret'));
    }
    await writeFile(tokenFile, JSON.stringify({access_token: 'replacement-secret', account_id: 'test-account'}));
    status = 200;
    await (await fetch(`${base}/responses`, { method: 'POST' })).text();
    assert.equal(calls.at(-1).headers.authorization, 'Bearer replacement-secret');
    await rm(tokenFile);
    assert.equal((await fetch(`${base}/responses`, { method: 'POST' })).status, 503);
  } finally {
    await new Promise(resolve => server.close(resolve));
    await rm(dir, { recursive: true });
  }
});
