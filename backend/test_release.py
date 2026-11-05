"""Stage 05 release/security checks. Provider inference stays disabled."""
import asyncio
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.release import ReleaseLimits
from app.providers.core import Config

@pytest.fixture
def static_client(tmp_path,monkeypatch):
    root=tmp_path/'dist';(root/'assets').mkdir(parents=True)
    (root/'index.html').write_text('<!doctype html><div id="root"></div>')
    (root/'assets/app-123.js').write_text('console.log("fixture")')
    monkeypatch.setattr(app.state,'frontend_dist',root)
    with TestClient(app) as c:yield c,root


def test_static_and_spa_routing(static_client):
    c,root=static_client
    assert c.get('/').status_code==200
    assert c.get('/workspace/outline',headers={'Accept':'text/html'}).text==(root/'index.html').read_text()
    js=c.get('/assets/app-123.js');assert js.status_code==200 and 'immutable' in js.headers['cache-control']
    assert c.get('/').headers['cache-control']=='no-store'
    for url in ['/api/does-not-exist','/assets/missing.js','/scenes/missing.svg']:
        assert c.get(url,headers={'Accept':'text/html'}).status_code==404


def test_private_files_and_symlinks_not_served(static_client,tmp_path):
    c,root=static_client
    outside=tmp_path/'secret.txt';outside.write_text('DO_NOT_SERVE')
    (root/'link.txt').symlink_to(outside)
    (root/'.env').write_text('DO_NOT_SERVE')
    for url in ['/link.txt','/.env','/%2e%2e/secret.txt','/x%00.txt']:
        r=c.get(url);assert r.status_code==404 and 'DO_NOT_SERVE' not in r.text


def test_security_headers_and_no_default_cors(static_client):
    c,_=static_client;r=c.get('/health',headers={'Origin':'https://other.invalid'})
    assert r.headers['x-content-type-options']=='nosniff'
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert 'access-control-allow-origin' not in r.headers

@pytest.mark.parametrize('path',['/','/health','/api/ai/availability','/api/not-a-route'])
def test_csp_allows_blob_reads_without_relaxing_other_security_headers(static_client,path):
    c,_=static_client
    response=c.get(path,headers={'Origin':'https://other.invalid'})
    policy=dict((parts[0],parts[1:]) for directive in response.headers['content-security-policy'].split(';')
                if (parts:=directive.split()))
    assert policy=={
        'default-src':["'self'"],'script-src':["'self'"],'style-src':["'self'"],
        'img-src':["'self'",'blob:','data:'],'connect-src':["'self'",'blob:'],
        'object-src':["'none'"],'base-uri':["'none'"],'frame-ancestors':["'none'"],'form-action':["'self'"]}
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-frame-options']=='DENY'
    assert response.headers['referrer-policy']=='no-referrer'
    assert 'access-control-allow-origin' not in response.headers


def test_readiness_requires_real_geometry_and_production_assets(monkeypatch,tmp_path):
    monkeypatch.setattr(app.state,'require_frontend',True)
    monkeypatch.setattr(app.state,'frontend_dist',tmp_path)
    r=TestClient(app).get('/ready')
    assert r.status_code==503 and r.json()['ai_required'] is False
    assert r.json()['checks']['frontend'] is False


def test_real_release_readiness():
    pytest.importorskip('shapely')
    r=TestClient(app).get('/ready')
    assert r.status_code==200 and r.json()['checks']['geometry']
    assert r.json()['checks']['scenes']


def test_geometry_json_body_limit():
    c=TestClient(app)
    assert c.post('/api/layouts',content=b'x'*(256*1024+1)).status_code==413


def test_chunked_size_limit_and_rate_admission():
    async def downstream(scope,receive,send):
        await receive();await send({'type':'http.response.start','status':200,'headers':[]});await send({'type':'http.response.body','body':b'ok'})
    async def run():
        wrapper=ReleaseLimits(downstream,rate=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapper),base_url='http://test') as c:
            async def chunks():yield b'x'*(256*1024);yield b'x'
            assert (await c.post('/api/layouts',content=chunks())).status_code==413
            assert (await c.post('/api/layouts',json={})).status_code==429
    asyncio.run(run())


def test_concurrent_geometry_jobs_are_rejected_not_queued():
    async def run():
        started=asyncio.Event();release=asyncio.Event()
        async def slow(scope,receive,send):
            await receive();started.set();await release.wait()
            await send({'type':'http.response.start','status':200,'headers':[]});await send({'type':'http.response.body','body':b'ok'})
        wrapper=ReleaseLimits(slow,jobs=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapper),base_url='http://test') as c:
            first=asyncio.create_task(c.post('/api/layouts',json={}));await started.wait()
            assert (await c.post('/api/layouts',json={})).status_code==429
            release.set();assert (await first).status_code==200
            assert (await c.post('/api/layouts',json={})).status_code==200
    asyncio.run(run())

@pytest.mark.parametrize('url',['https://169.254.169.254/model','https://10.0.0.1/model','https://host.invalid:wrong/model','https://name:secret@host.invalid/model','https://host.invalid/model?secret=x'])
def test_unsafe_provider_configuration_fails_closed(url):
    c=Config(provider='modal',endpoint=url,model='id',auth='none')
    assert c.problem('segmentation') is not None


def test_geometry_complexity_limit():
    pytest.importorskip('shapely')
    from app.geometry import from_geojson
    with pytest.raises(ValueError):from_geojson({'type':'Polygon','coordinates':[[[i,0] for i in range(2049)]]})


def test_cors_only_configured_origin(monkeypatch):
    from fastapi import FastAPI
    from app.release import configure
    monkeypatch.setenv('CORS_ORIGINS','https://ui.example')
    test_app=FastAPI();configure(test_app);c=TestClient(test_app)
    good=c.options('/api/layouts',headers={'Origin':'https://ui.example','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Content-Type'})
    assert good.status_code==200 and good.headers['access-control-allow-origin']=='https://ui.example'
    bad=c.options('/api/layouts',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})
    assert bad.status_code==400 and 'access-control-allow-origin' not in bad.headers
