import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from . import __version__
from .paths import resource_path
from .sessions import ServiceError, SessionManager


class StartRequest(BaseModel):
    actions: list[Literal['blink', 'mouth', 'turn_left', 'turn_right']] | None = Field(None, min_length=1, max_length=4)
    cameraIndex: int = Field(0, ge=0, le=9)
    requireConsent: bool = True


class ConsentRequest(BaseModel):
    nonce: str = Field(min_length=1, max_length=128)
    allow: bool = True


class PublicCors:
    def __init__(self, app):
        self.app = app
        self.cors = CORSMiddleware(app, allow_origins=['*'], allow_credentials=False,
                                   allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
                                   allow_headers=['Authorization', 'Content-Type'])

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        target = self.cors if path.startswith('/capture/') or path in ('/health', '/capture-sdk.js') else self.app
        await target(scope, receive, send)


def create_app(manager=None):
    manager = manager or SessionManager()

    @asynccontextmanager
    async def lifespan(app):
        async def cleaner():
            while True:
                await asyncio.sleep(.5)
                manager.sweep()
        task = asyncio.create_task(cleaner())
        yield
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        await asyncio.to_thread(manager.close)

    app = FastAPI(title='Face Capture', version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.add_middleware(PublicCors)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse({'errorCode': exc.code, 'message': exc.message}, status_code=exc.status)

    def token(request):
        auth = request.headers.get('authorization', '')
        return auth[7:] if auth.startswith('Bearer ') else ''

    def local_consent(request):
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.url.netloc}'
        if request.headers.get('sec-fetch-site') != 'same-origin' or (origin and origin != expected):
            raise ServiceError('LOCAL_CONFIRMATION_REQUIRED', '请在本地授权页面确认', 403)
        if request.method == 'POST' and origin != expected:
            raise ServiceError('LOCAL_CONFIRMATION_REQUIRED', '请在本地授权页面确认', 403)

    @app.get('/health')
    def health():
        return {'service': 'face-capture', 'version': __version__, 'status': 'ok',
                'modelReady': resource_path('models/face_landmarker.task').is_file()}

    @app.get('/')
    def index(): return FileResponse(resource_path('web/index.html'))

    @app.get('/authorize')
    def authorize(): return FileResponse(resource_path('web/authorize.html'))

    @app.get('/capture-sdk.js')
    def sdk(): return FileResponse(resource_path('web/capture-sdk.js'), media_type='text/javascript')

    @app.get('/consent/{sid}')
    def consent_info(sid: str, request: Request):
        local_consent(request)
        return manager.consent_info(sid)

    @app.post('/consent/{sid}')
    def consent(sid: str, body: ConsentRequest, request: Request):
        local_consent(request)
        if body.allow: manager.approve(sid, body.nonce)
        else: manager.deny(sid, body.nonce)
        return {'ok': True}

    @app.post('/capture/sessions', status_code=201)
    def start(body: StartRequest):
        return manager.create(body.actions, body.cameraIndex, require_consent=body.requireConsent)

    @app.get('/capture/sessions/{sid}')
    def status(sid: str, request: Request): return manager.snapshot(sid, token(request))

    @app.delete('/capture/sessions/{sid}')
    def cancel(sid: str, request: Request):
        manager.cancel_session(sid, token(request))
        return {'ok': True}

    @app.get('/capture/sessions/{sid}/preview')
    def preview(sid: str, request: Request):
        return Response(manager.image(sid, token(request), 'preview'), media_type='image/jpeg')

    @app.get('/capture/sessions/{sid}/photo')
    def photo(sid: str, request: Request):
        return Response(manager.image(sid, token(request), 'photo'), media_type='image/jpeg')

    @app.websocket('/capture/sessions/{sid}/stream')
    async def stream(websocket: WebSocket, sid: str):
        await websocket.accept()

        async def close_after_delivery(code):
            try:
                event = await asyncio.wait_for(websocket.receive(), 5)
                if event['type'] == 'websocket.disconnect':
                    return
            except asyncio.TimeoutError:
                pass
            await websocket.close(code=code)

        try:
            # Browser WebSocket cannot set Authorization headers. Keep tokens out of URLs.
            auth = await asyncio.wait_for(websocket.receive_json(), 5)
            if not isinstance(auth, dict) or auth.get('type') != 'auth' or not isinstance(auth.get('token'), str):
                raise ServiceError('UNAUTHORIZED', '采集会话令牌无效', 401)
            key = auth['token']
            manager.authenticate(sid, key)
            previous_state, previous_frame = None, None
            while True:
                # Copy only the latest frame under the lock; never queue camera frames.
                with manager.lock:
                    state = manager.snapshot(sid, key)
                    frame = manager.authenticate(sid, key).preview
                if state != previous_state:
                    await asyncio.wait_for(websocket.send_json({'type': 'status', 'state': state}), 5)
                    previous_state = state
                if state['status'] in ('passed', 'failed', 'expired', 'cancelled'):
                    # Let the client consume the final message and initiate closing.
                    # wsproto closes TCP immediately on server close; on Windows that
                    # can race the final message and appear as an abnormal disconnect.
                    await close_after_delivery(1000)
                    return
                if frame is not None and frame is not previous_frame:
                    await asyncio.wait_for(websocket.send_bytes(frame), 5)
                    previous_frame = frame
                # One batch in flight. ACK also proves the browser is still responsive.
                await asyncio.wait_for(websocket.send_json({'type': 'sync'}), 5)
                ack = await asyncio.wait_for(websocket.receive_json(), 5)
                if not isinstance(ack, dict) or ack.get('type') != 'ack':
                    await websocket.close(code=1008)
                    return
                await asyncio.sleep(.1)
        except ServiceError as exc:
            await websocket.send_json({'type': 'error', 'errorCode': exc.code, 'message': exc.message})
            await close_after_delivery(1008)
        except (ValueError, KeyError, asyncio.TimeoutError):
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            pass

    return app
