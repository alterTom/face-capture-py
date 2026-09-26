import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import vm from 'node:vm';
import { parse, compileScript } from '@vue/compiler-sfc';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
for (const key of ['window', 'document', 'Element', 'HTMLElement', 'SVGElement']) {
  globalThis[key] = dom.window[key];
}
const { createApp, nextTick, h, reactive } = await import('vue');
const source = new URL('../src/components/FaceCapture.vue', import.meta.url);
const generated = new URL('./.compiled-component.mjs', import.meta.url);
let Component;
try {
  const { descriptor } = parse(await readFile(source, 'utf8'));
  const compiled = compileScript(descriptor, { id: 'face-test', inlineTemplate: true });
  await writeFile(generated, compiled.content);
  Component = (await import(generated.href)).default;
} finally {
  await unlink(generated).catch(() => {});
}

function mount(props = {}) {
  const calls = [], events = [], revoked = [];
  let nextUrl = 0;
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => `blob:test-${++nextUrl}`;
  URL.revokeObjectURL = url => revoked.push(url);
  window.FaceCaptureClient = class {
    capture(options) {
      return new Promise((resolve, reject) => calls.push({ options, resolve, reject, cancelled: false, client: this }));
    }
    cancel() { const call = calls.find(c => c.client === this); if (call) call.cancelled = true; }
  };
  const host = document.createElement('div');
  document.body.append(host);
  const settings = reactive({ autoStart: false, ...props });
  let instance;
  const app = createApp({ render: () => h(Component, {
    ...settings,
    ref: value => { if (value) instance = value; },
    onSuccess: data => events.push(['success', data]),
    onError: error => events.push(['error', error]),
    onCancel: () => events.push(['cancel']),
    onStatus: data => events.push(['status', data]),
    'onUpdate:active': value => events.push(['update:active', value]),
    onClose: reason => events.push(['close', reason])
  }) });
  app.mount(host);
  let unmounted = false;
  return { instance, host, calls, events, revoked, settings,
    unmount() { if (!unmounted) { app.unmount(); unmounted = true; } },
    cleanup() {
      this.unmount(); host.remove();
      URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke;
      delete window.FaceCaptureClient;
    }
  };
}

test('each round sends exactly one supported action and returns the photo with that action', async t => {
  let sample = 0;
  t.mock.method(Math, 'random', () => (sample++ % 4) / 4);
  const f = mount();
  try {
    for (let i = 0; i < 8; i++) {
      const pending = f.instance.start();
      const call = f.calls.at(-1);
      assert.equal(call.options.actions.length, 1);
      assert.ok(['blink', 'mouth', 'turn_left', 'turn_right'].includes(call.options.actions[0]));
      assert.equal(call.options.actions[0], ['blink', 'mouth', 'turn_left', 'turn_right'][i % 4]);
      const blob = new Blob(['jpeg'], { type: 'image/jpeg' });
      call.resolve(blob);
      const result = await pending;
      await nextTick();
      assert.equal(result.blob, blob);
      assert.equal(result.action, call.options.actions[0]);
      assert.equal(f.events.at(-1)[0], 'success');
      assert.ok(f.host.querySelector('img'));
      assert.equal(f.host.querySelector('button'), null);
    }
  } finally { f.cleanup(); }
});

test('cancel invalidates late preview, progress and result while a new round can succeed', async () => {
  const f = mount();
  try {
    const first = f.instance.start();
    f.calls[0].options.onPreview(new Blob(['frame']));
    await nextTick();
    f.instance.cancel();
    assert.equal(f.calls[0].cancelled, true);
    assert.ok(f.revoked.includes('blob:test-1'));
    const second = f.instance.start();
    f.calls[0].options.onPreview(new Blob(['stale']));
    f.calls[0].options.onStatus({ prompt: 'stale' });
    f.calls[0].resolve(new Blob(['stale']));
    assert.equal(await first, null);
    assert.equal(f.events.some(e => e[0] === 'success' || e[0] === 'status'), false);
    f.calls[1].resolve(new Blob(['new']));
    assert.equal(await (await second).blob.text(), 'new');
    assert.equal(f.events.filter(e => e[0] === 'success').length, 1);
  } finally { f.cleanup(); }
});

test('duplicate starts do not open another session; preview URLs are released on replacement and unmount', async () => {
  const f = mount();
  try {
    const pending = f.instance.start();
    assert.equal(await f.instance.start(), null);
    assert.equal(f.calls.length, 1);
    f.calls[0].options.onPreview(new Blob(['one']));
    f.calls[0].options.onPreview(new Blob(['two']));
    assert.ok(f.revoked.includes('blob:test-1'));
    f.unmount();
    assert.equal(f.calls[0].cancelled, true);
    assert.ok(f.revoked.includes('blob:test-2'));
    f.calls[0].resolve(new Blob(['late']));
    assert.equal(await pending, null);
    assert.equal(f.events.some(e => e[0] === 'success'), false);
  } finally { f.cleanup(); }
});

test('service failures emit error and allow retry without an unhandled rejection', async () => {
  const f = mount({ actionPool: ['mouth'], cameraIndex: 2 });
  try {
    const pending = f.instance.start();
    assert.deepEqual(f.calls[0].options.actions, ['mouth']);
    assert.equal(f.calls[0].options.cameraIndex, 2);
    const error = Object.assign(new Error('camera busy'), { code: 'CAMERA_BUSY' });
    f.calls[0].reject(error);
    assert.equal(await pending, null);
    assert.equal(f.events.at(-1)[1], error);
    const retry = f.instance.start();
    f.calls[1].resolve(new Blob(['ok']));
    assert.ok(await retry);
  } finally { f.cleanup(); }
});

test('invalid action pool and missing SDK report actionable errors without creating sessions', async () => {
  for (const actionPool of [[], ['unknown']]) {
    const f = mount({ actionPool });
    try {
      assert.equal(await f.instance.start(), null);
      assert.equal(f.calls.length, 0);
      assert.equal(f.events.at(-1)[1].code, 'INVALID_ACTION_POOL');
    } finally { f.cleanup(); }
  }
  const f = mount();
  try {
    delete window.FaceCaptureClient;
    assert.equal(await f.instance.start(), null);
    assert.equal(f.events.at(-1)[1].code, 'SDK_NOT_LOADED');
  } finally { f.cleanup(); }
});

test('hiding a mounted dialog aborts capture and does not start again when reopened', async () => {
  const f = mount({ active: true });
  try {
    const pending = f.instance.start();
    f.settings.active = false;
    await nextTick();
    assert.equal(f.calls[0].cancelled, true);
    f.calls[0].resolve(new Blob(['late']));
    assert.equal(await pending, null);
    assert.equal(await f.instance.start(), null);
    f.settings.active = true;
    await nextTick();
    assert.equal(f.calls.length, 1);
    assert.equal(f.events.some(e => e[0] === 'success'), false);
  } finally { f.cleanup(); }
});

test('component and real SDK send a single action and deliver the JPEG from the service', async () => {
  const f = mount({ actionPool: ['turn_right'] });
  const requests = [];
  try {
    const code = await readFile(new URL('../../../web/capture-sdk.js', import.meta.url), 'utf8');
    const json = data => new Response(JSON.stringify(data));
    vm.runInNewContext(code, {
      window,
      location: { origin: 'http://127.0.0.1:18765' },
      URL, AbortController, AbortSignal, DOMException, Date, setTimeout, clearTimeout,
      fetch: async (url, options) => {
        requests.push({ url, options });
        if (options.method === 'DELETE') return json({ ok: true });
        if (url.endsWith('/capture/sessions')) return json({ sessionId: 'test', token: 'secret' });
        if (url.includes('/consent/')) return json({ nonce: 'nonce' });
        if (url.endsWith('/photo')) return new Response('jpeg-bytes', { headers: { 'Content-Type': 'image/jpeg' } });
        return json({ status: 'passed', prompt: '采集成功', actions: ['turn_right'] });
      }
    });
    const result = await f.instance.start();
    assert.deepEqual(JSON.parse(requests[0].options.body), { actions: ['turn_right'], cameraIndex: 0, requireConsent: false });
    assert.equal(result.blob.type, 'image/jpeg');
    assert.equal(await result.blob.text(), 'jpeg-bytes');
    assert.equal(f.events.filter(e => e[0] === 'success').length, 1);
    const photo = requests.find(r => r.url.endsWith('/photo'));
    assert.equal(photo.options.headers.Authorization, 'Bearer secret');
    assert.ok(requests.some(r => r.options.method === 'DELETE'));
  } finally { f.cleanup(); }
});

test('auto capture requests direct mode; loading ring stops on first preview and result stays until caller closes', async () => {
  const f = mount({ autoStart: true, active: false });
  try {
    f.settings.active = true;
    await nextTick();
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].options.requireConsent, false);
    assert.ok(f.host.querySelector('.face-capture__ring--connecting'));
    assert.equal(f.host.querySelector('button'), null);
    f.calls[0].options.onStatus({ status: 'running', prompt: '正在初始化模型和摄像头' });
    await nextTick();
    assert.ok(f.host.querySelector('.face-capture__ring--connecting'));
    f.calls[0].options.onPreview(new Blob(['preview']));
    await nextTick();
    assert.equal(f.host.querySelector('.face-capture__ring--connecting'), null);
    const blob = new Blob(['jpeg'], { type: 'image/jpeg' });
    f.calls[0].resolve(blob);
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(f.events.at(-1)[0], 'success');
    assert.equal(f.events.at(-1)[1].blob, blob);
    assert.equal(f.events.some(e => e[0] === 'close' || e[0] === 'update:active'), false);
    assert.ok(f.host.querySelector('img'));
    f.settings.active = false;
    await nextTick();
    assert.equal(f.host.querySelector('img'), null);
  } finally { f.cleanup(); }
});

test('caller can cancel and retry; errors stop loading without closing the caller dialog', async () => {
  const f = mount({ autoStart: true });
  try {
    f.calls[0].reject(new Error('连接失败'));
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(f.instance.connecting, false);
    assert.equal(f.events.at(-1)[0], 'error');
    assert.equal(f.events.some(e => e[0] === 'close'), false);
    const pending = f.instance.start();
    assert.equal(f.calls.length, 2);
    f.instance.cancel();
    assert.equal(f.calls[1].cancelled, true);
    assert.equal(f.instance.connecting, false);
    f.calls[1].resolve(new Blob(['late']));
    assert.equal(await pending, null);
    assert.equal(f.events.some(e => e[0] === 'success'), false);
  } finally { f.cleanup(); }
});
