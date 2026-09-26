/* Copy this file to your business site's own origin. No dependencies. */
(function (root) {
  'use strict';
  class FaceCaptureClient {
    constructor(baseUrl = 'http://127.0.0.1:18765') {
      this.baseUrl = baseUrl.replace(/\/$/, '');
      this.active = null;
    }
    async health() {
      const response = await fetch(this.baseUrl + '/health', {
        cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(5000)
      });
      if (!response.ok) throw new Error('本地服务不可用');
      const data = await response.json();
      if (data.service !== 'face-capture') throw new Error('端口被其他程序占用');
      return data;
    }
    cancel() { this.active?.abort(); }
    async stream(path, token, signal, consentTab, onStatus, onPreview) {
      if (typeof WebSocket === 'undefined') return false;
      return new Promise((resolve, reject) => {
        let socket, timer, settled = false, lastMessage = Date.now();
        const deadline = Date.now() + 130000;
        let pendingConsent = false;
        const finish = (error, passed = false) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          signal.removeEventListener('abort', abort);
          if (socket) {
            socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
            socket.close();
          }
          if (error) reject(error); else resolve(passed);
        };
        const abort = () => finish(new DOMException('采集已取消', 'AbortError'));
        if (signal.aborted) { abort(); return; }
        signal.addEventListener('abort', abort, {once:true});
        try {
          const url = new URL(this.baseUrl + path + '/stream');
          url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
          socket = new WebSocket(url.href);
          socket.binaryType = 'blob';
          socket.onopen = () => socket.send(JSON.stringify({type:'auth', token}));
          socket.onerror = socket.onclose = () => finish(null);
          socket.onmessage = event => {
            if (settled || signal.aborted) return;
            lastMessage = Date.now();
            try {
              if (typeof event.data !== 'string') { onPreview(event.data); return; }
              const message = JSON.parse(event.data);
              if (message.type === 'sync') {
                socket.send(JSON.stringify({type:'ack'}));
              } else if (message.type === 'error') {
                finish(Object.assign(new Error(message.message), {code:message.errorCode}));
              } else if (message.type === 'status') {
                const state = message.state;
                pendingConsent = state.status === 'pending_consent';
                onStatus(state);
                if (signal.aborted || settled) return;
                if (state.status === 'passed') finish(null, true);
                else if (['failed', 'expired', 'cancelled'].includes(state.status)) {
                  finish(Object.assign(new Error(state.prompt), {code:state.errorCode}));
                }
              }
            } catch (error) { finish(error); }
          };
          const watch = () => {
            if (settled) return;
            if (pendingConsent && consentTab?.closed) return finish(new Error('授权页已关闭，采集未开始'));
            if (Date.now() > deadline) return finish(new Error('等待采集超时'));
            if (Date.now() - lastMessage > 8000) return finish(null);
            timer = setTimeout(watch, 1000);
          };
          timer = setTimeout(watch, 1000);
        } catch (_) { finish(null); }
      });
    }
    async capture({actions, cameraIndex = 0, requireConsent = true, onStatus = () => {}, onPreview = () => {}} = {}) {
      if (this.active) throw new Error('已有采集任务');
      const controller = new AbortController();
      this.active = controller;
      const local = location.origin === new URL(this.baseUrl).origin;
      // Open synchronously from the user's click, before the first await.
      const consentTab = !requireConsent || local ? null : window.open('about:blank', '_blank');
      let session = null;
      const request = async (path, options = {}) => {
        const response = await fetch(this.baseUrl + path, {
          ...options, credentials: 'omit', cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
          headers: {...(session ? {Authorization: 'Bearer ' + session.token} : {}), ...options.headers}
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          const error = new Error(detail.message || `请求失败 (${response.status})`);
          error.status = response.status;
          error.code = detail.errorCode;
          throw error;
        }
        return response;
      };
      try {
        if (requireConsent && !local && !consentTab) throw new Error('请允许弹出浏览器授权页后重试');
        if (consentTab) {
          consentTab.opener = null;
          consentTab.document.body.textContent = '正在连接本地人脸采集程序…';
        }
        session = await (await request('/capture/sessions', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({actions, cameraIndex, requireConsent})
        })).json();
        if (!requireConsent && session.status === 'pending_consent') {
          throw Object.assign(new Error('本机采集程序版本过旧，请升级到支持直接采集的版本'), {
            code: 'DIRECT_CAPTURE_UNSUPPORTED'
          });
        }
        if (requireConsent && local) {
          const info = await (await request('/consent/' + session.sessionId)).json();
          await request('/consent/' + session.sessionId, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nonce: info.nonce})
          });
        } else if (requireConsent) {
          consentTab.location.replace(this.baseUrl + session.authorizeUrl);
        }
        const path = '/capture/sessions/' + session.sessionId;
        if (await this.stream(path, session.token, controller.signal, consentTab, onStatus, onPreview)) {
          return await (await request(path + '/photo')).blob();
        }
        // Old services or interrupted connections use the same session via HTTP.
        let lastPreview = 0;
        let previewPending = false;
        const deadline = Date.now() + 130000;
        while (Date.now() < deadline) {
          const state = await (await request(path)).json();
          onStatus(state);
          if (state.status === 'passed') return await (await request(path + '/photo')).blob();
          if (['failed', 'expired', 'cancelled'].includes(state.status)) {
            const error = new Error(state.prompt);
            error.code = state.errorCode;
            throw error;
          }
          if (state.status === 'pending_consent' && consentTab?.closed) {
            throw new Error('授权页已关闭，采集未开始');
          }
          if (state.status === 'running' && !previewPending && Date.now() - lastPreview > 100) {
            previewPending = true;
            lastPreview = Date.now();
            // Preview is best effort; a slow frame must not block completion polling.
            request(path + '/preview').then(r => r.blob()).then(blob => {
              if (!controller.signal.aborted) onPreview(blob);
            }).catch(() => {}).finally(() => { previewPending = false; });
          }
          await new Promise((resolve, reject) => {
            const abort = () => { clearTimeout(timer); reject(new DOMException('采集已取消', 'AbortError')); };
            const timer = setTimeout(() => { controller.signal.removeEventListener('abort', abort); resolve(); }, 100);
            if (controller.signal.aborted) abort();
            else controller.signal.addEventListener('abort', abort, {once: true});
          });
        }
        throw new Error('等待采集超时');
      } catch (error) {
        if (error.name === 'TypeError') {
          throw new Error('无法连接采集服务。请先启动桌面快捷方式，并检查浏览器本地网络访问权限。');
        }
        throw error;
      } finally {
        controller.abort();
        if (session) {
          // Release data in the background so cleanup cannot delay photo display.
          void fetch(this.baseUrl + '/capture/sessions/' + session.sessionId, {
            method: 'DELETE', credentials: 'omit', keepalive: true,
            headers: {Authorization: 'Bearer ' + session.token}, signal: AbortSignal.timeout(3000)
          }).catch(() => {});
        }
        try { if (consentTab && !consentTab.closed) consentTab.close(); } catch (_) {}
        this.active = null;
      }
    }
  }
  root.FaceCaptureClient = FaceCaptureClient;
})(typeof window === 'undefined' ? globalThis : window);
