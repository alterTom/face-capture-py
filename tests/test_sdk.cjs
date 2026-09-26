const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('web/capture-sdk.js', 'utf8');

function setup(fetch, options = {}) {
  const sandbox = {window: options.window || {}, location: {origin:options.origin || 'http://127.0.0.1:18765'},
    URL, AbortController, AbortSignal, DOMException, Date, setTimeout, clearTimeout, fetch,
    WebSocket: options.WebSocket};
  vm.runInNewContext(code, sandbox);
  return new sandbox.window.FaceCaptureClient();
}
const response = data => new Response(JSON.stringify(data), {headers:{'Content-Type':'application/json'}});
const passed = {status:'passed', prompt:'采集成功'};

test('WebSocket delivers preview and status without HTTP polling, then closes', async () => {
  let socket, previews = 0;
  class FakeSocket {
    constructor(url) { socket = this; this.url = url; queueMicrotask(() => this.onopen()); }
    send(data) {
      const message = JSON.parse(data);
      if (message.type === 'auth') {
        assert.equal(message.token, 'secret');
        queueMicrotask(() => {
          this.onmessage({data: new Blob(['preview'])});
          this.onmessage({data: JSON.stringify({type:'status', state:passed})});
        });
      }
    }
    close() { this.closed = true; }
  }
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') return response({ok:true});
    if (url.endsWith('/capture/sessions')) return response({sessionId:'ws',token:'secret',status:'running'});
    assert.ok(url.endsWith('/photo'), 'unexpected polling: ' + url);
    return new Response('final');
  }, {WebSocket:FakeSocket});
  const result = await client.capture({requireConsent:false, onPreview:()=>previews++});
  assert.equal(await result.text(), 'final');
  assert.equal(previews, 1);
  assert.equal(socket.url, 'ws://127.0.0.1:18765/capture/sessions/ws/stream');
  assert.equal(socket.closed, true);
});

test('WebSocket disconnect falls back to HTTP on the same session', async () => {
  let creates = 0, closed = false;
  class BrokenSocket {
    constructor() { queueMicrotask(() => this.onclose()); }
    close() { closed = true; }
  }
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') return response({ok:true});
    if (url.endsWith('/capture/sessions')) { creates++; return response({sessionId:'one',token:'secret',status:'running'}); }
    if (url.endsWith('/photo')) return new Response('jpeg');
    return response(passed);
  }, {WebSocket:BrokenSocket});
  assert.equal(await (await client.capture({requireConsent:false})).text(), 'jpeg');
  assert.equal(creates, 1);
  assert.equal(closed, true);
});

test('cancel closes the socket, rejects capture and ignores queued callbacks', async () => {
  let socket, ready, previews = 0, deleted = false;
  const opened = new Promise(resolve => ready = resolve);
  class WaitingSocket {
    constructor() { socket = this; queueMicrotask(() => { this.late = this.onmessage; ready(); }); }
    close() { this.closed = true; }
  }
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') { deleted = true; return response({ok:true}); }
    return response({sessionId:'one',token:'secret',status:'running'});
  }, {WebSocket:WaitingSocket});
  const pending = client.capture({requireConsent:false,onPreview:()=>previews++});
  await opened;
  client.cancel();
  await assert.rejects(pending, {name:'AbortError'});
  socket.late({data:new Blob(['late'])});
  assert.equal(previews, 0);
  assert.equal(socket.closed, true);
  assert.equal(deleted, true);
  assert.equal(client.active, null);
});

test('WebSocket task failure is not retried through HTTP', async () => {
  class FailedSocket {
    constructor() { queueMicrotask(() => this.onmessage({data:JSON.stringify({type:'status',state:{status:'failed',prompt:'camera missing',errorCode:'CAMERA_UNAVAILABLE'}})})); }
    close() {}
  }
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') return response({ok:true});
    assert.ok(url.endsWith('/capture/sessions'));
    return response({sessionId:'one',token:'secret',status:'running'});
  }, {WebSocket:FailedSocket});
  await assert.rejects(client.capture({requireConsent:false}), {code:'CAMERA_UNAVAILABLE'});
});

test('photo is returned without waiting for a slow cleanup response', async () => {
  let releaseCleanup;
  const cleanup = new Promise(resolve => releaseCleanup = resolve);
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') return cleanup;
    if (url.endsWith('/capture/sessions')) return response({sessionId:'one',token:'secret'});
    if (url.includes('/consent/')) return response({nonce:'nonce'});
    if (url.endsWith('/photo')) return new Response('jpeg', {headers:{'Content-Type':'image/jpeg'}});
    return response(passed);
  });
  try {
    const result = await Promise.race([client.capture(), new Promise(resolve => setTimeout(()=>resolve('blocked'),100))]);
    assert.notEqual(result, 'blocked', 'cleanup delayed the photo result');
    assert.equal(await result.text(), 'jpeg');
  } finally { releaseCleanup(response({ok:true})); }
});

test('direct capture from business origin opens no consent window and returns JPEG', async () => {
  let opened = false, submitted;
  const client = setup(async (url, options) => {
    assert.ok(!url.includes('/consent/'));
    if (options.method === 'DELETE') return response({ok:true});
    if (url.endsWith('/capture/sessions')) {
      submitted = JSON.parse(options.body);
      return response({sessionId:'direct', token:'secret', status:'running', authorizeUrl:null});
    }
    if (url.endsWith('/photo')) return new Response('jpeg');
    return response(passed);
  }, {origin:'https://business.example', window:{open(){ opened = true; return null; }}});
  const blob = await client.capture({actions:['blink'], requireConsent:false});
  assert.equal(opened, false);
  assert.equal(submitted.requireConsent, false);
  assert.equal(await blob.text(), 'jpeg');
});

test('direct capture reports outdated service immediately and cleans the pending session', async () => {
  let cleaned = false;
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') { cleaned = true; return response({ok:true}); }
    assert.ok(url.endsWith('/capture/sessions'));
    return response({sessionId:'old', token:'secret', status:'pending_consent'});
  });
  await assert.rejects(client.capture({requireConsent:false}), {code:'DIRECT_CAPTURE_UNSUPPORTED'});
  assert.equal(cleaned, true);
});

test('a slow preview does not block successful status and photo retrieval', async () => {
  let polls = 0, releasePreview, latePreviews = 0;
  const preview = new Promise(resolve => releasePreview = resolve);
  const client = setup(async (url, options) => {
    if (options.method === 'DELETE') return response({ok:true});
    if (url.endsWith('/capture/sessions')) return response({sessionId:'two',token:'secret'});
    if (url.includes('/consent/')) return response({nonce:'nonce'});
    if (url.endsWith('/preview')) return preview;
    if (url.endsWith('/photo')) return new Response('jpeg');
    return response(++polls === 1 ? {status:'running'} : passed);
  });
  try {
    const result = await Promise.race([client.capture({onPreview:()=>latePreviews++}),
      new Promise(resolve => setTimeout(()=>resolve('blocked'),400))]);
    assert.notEqual(result, 'blocked', 'preview blocked completion polling');
    assert.equal(await result.text(), 'jpeg');
  } finally { releasePreview(new Response('preview')); }
  await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(latePreviews, 0, 'preview callback fired after task completion');
});
