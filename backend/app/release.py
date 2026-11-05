"""Stage 05: single-service packaging, bounded admission and release health."""
import asyncio
import json
import os
from collections import deque
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

ROOT=Path(__file__).resolve().parents[2]
CSP="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"

class ReleaseLimits:
    def __init__(self,app, jobs=2, rate=60, ai_rate=10, body_timeout=15):
        self.app=app;self.slots=BoundedSemaphore(jobs);self.rate=rate;self.ai_rate=ai_rate
        self.events=deque();self.ai_events=deque();self.lock=Lock();self.body_timeout=body_timeout

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        path=scope['path']; expensive=scope['method']=='POST' and (path.startswith('/api/layouts') or path in ('/api/ai/segment','/api/ai/recommend','/api/ai/detect-material','/api/ai/cutting-ideas'))
        async def secure(message):
            if message['type']=='http.response.start':
                message.setdefault('headers',[]).extend([(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer'),(b'x-frame-options',b'DENY'),(b'content-security-policy',CSP.encode())])
            await send(message)
        async def error(status,detail):
            await JSONResponse({'detail':detail},status_code=status,headers={'Retry-After':'60'} if status==429 else {})(scope,receive,secure)
        if len(scope.get('query_string',b''))>8192:return await error(414,'query_too_large')
        acquired=False
        if expensive:
            with self.lock:
                now=monotonic()
                for events in (self.events,self.ai_events):
                    while events and now-events[0]>=60:events.popleft()
                ai=path.startswith('/api/ai/')
                limited=len(self.events)>=self.rate or (ai and len(self.ai_events)>=self.ai_rate)
                if not limited:
                    self.events.append(now)
                    if ai:self.ai_events.append(now)
            if limited:return await error(429,'request_budget_exhausted')
            acquired=self.slots.acquire(blocking=False)
            if not acquired:return await error(429,'geometry_service_busy')
        try:
            if scope['method'] in ('POST','PUT','PATCH') and path.startswith('/api/'):
                limit=8*1024*1024 if path in ('/api/ai/segment','/api/ai/detect-material') else 256*1024
                headers=dict(scope.get('headers',[]))
                try:length=int(headers.get(b'content-length',b'0'))
                except ValueError:return await error(400,'invalid_content_length')
                if length<0 or length>limit:return await error(413,'request_too_large')
                body=bytearray()
                async def read():
                    while True:
                        message=await receive()
                        if message['type']=='http.disconnect':return False
                        body.extend(message.get('body',b''))
                        if len(body)>limit:raise OverflowError()
                        if not message.get('more_body'):return True
                try:
                    if not await asyncio.wait_for(read(),self.body_timeout):return
                except OverflowError:return await error(413,'request_too_large')
                except asyncio.TimeoutError:return await error(408,'request_body_timeout')
                delivered=False
                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered=True
                        return {'type':'http.request','body':bytes(body),'more_body':False}
                    return await receive()
                await self.app(scope,replay,secure)
            else:await self.app(scope,receive,secure)
        finally:
            if acquired:self.slots.release()


def configure(app):
    def integer(name,default,low,high):
        value=int(os.getenv(name,str(default)))
        if not low<=value<=high:raise ValueError(name+' outside permitted range')
        return value
    app.add_middleware(ReleaseLimits,jobs=integer('GEOMETRY_MAX_CONCURRENCY',2,1,4),rate=integer('EXPENSIVE_REQUESTS_PER_MINUTE',60,1,600),ai_rate=integer('AI_REQUESTS_PER_MINUTE',10,1,60),body_timeout=integer('REQUEST_BODY_TIMEOUT_SECONDS',15,1,60))
    origins=[v.strip() for v in os.getenv('CORS_ORIGINS','').split(',') if v.strip()]
    from urllib.parse import urlsplit
    for origin in origins:
        u=urlsplit(origin)
        if u.scheme not in ('http','https') or not u.netloc or u.path or u.query or u.fragment or u.username or u.password:raise ValueError('CORS_ORIGINS must contain explicit origins')
    if origins:app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type'])
    app.state.frontend_dist=Path(os.getenv('FRONTEND_DIST',str(ROOT/'frontend/dist'))).resolve()
    app.state.require_frontend=os.getenv('REQUIRE_FRONTEND','false').lower()=='true'

    @app.get('/ready')
    def ready():
        checks={}
        try:
            from shapely.geometry import box
            from .geometry import valid_material
            checks['geometry']=valid_material(box(0,0,1,1)).area==1
        except (ImportError,ValueError,OSError):checks['geometry']=False
        try:
            from PIL import Image
            checks['image_decoder']=bool(Image.registered_extensions())
        except (ImportError,ValueError,OSError):checks['image_decoder']=False
        try:
            import cv2
            checks['image_processing']=callable(cv2.grabCut) and callable(cv2.findContours)
        except (ImportError,ValueError,OSError):checks['image_processing']=False
        data=json.loads((ROOT/'backend/app/scenes.json').read_text())
        checks['scenes']=len([s for s in data if s['id'].startswith('scene-')])==12 and all((ROOT/'public'/s[k].lstrip('/')).is_file() for s in data for k in ('image','mask'))
        checks['frontend']=(app.state.frontend_dist/'index.html').is_file() and bool(list((app.state.frontend_dist/'assets').glob('*.js')))
        checks['packaged_scenes']=all((app.state.frontend_dist/s[k].lstrip('/')).is_file() for s in data for k in ('image','mask'))
        required=['geometry','image_decoder','image_processing','scenes']+(['frontend','packaged_scenes'] if app.state.require_frontend else [])
        ok=all(checks[k] for k in required)
        return JSONResponse({'status':'ready' if ok else 'not_ready','checks':checks,'ai_required':False},status_code=200 if ok else 503)

    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str,request:Request):
        if path.split('/')[0] in ('api','health','ready','docs','redoc','openapi.json'):
            raise HTTPException(404,'Not found')
        root=app.state.frontend_dist
        if len(path)>2048 or '\x00' in path:raise HTTPException(404,'Not found')
        target=(root/path).resolve()
        if not target.is_relative_to(root) or any(p.startswith('.') for p in Path(path).parts) or '\x00' in path:
            raise HTTPException(404,'Not found')
        if target.is_file():
            return FileResponse(target,headers={'Cache-Control':'public, max-age=31536000, immutable' if path.startswith('assets/') else ('no-store' if path=='index.html' else 'no-cache')})
        if Path(path).suffix or (path and 'text/html' not in request.headers.get('accept','')):
            raise HTTPException(404,'Not found')
        index=root/'index.html'
        if not index.is_file():raise HTTPException(503,'Frontend build is unavailable')
        return FileResponse(index,headers={'Cache-Control':'no-store'})
