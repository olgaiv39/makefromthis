"""TEST DOUBLES ONLY: httpx.MockTransport; no live inference or credentials."""
import asyncio
import io
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.providers.core import Config, Runtime, ProviderError

TOKEN='TEST_ONLY_NOT_A_CREDENTIAL'
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app.state,'ai_runtime',Runtime(enabled=False))
    with TestClient(app) as c: yield c

def config(provider='modal', **kwargs):
    return Config(provider=provider,endpoint='https://test.invalid/infer',model='TEST_MODEL',token=TOKEN,auth='bearer',**kwargs)

def install(response=None, handler=None, **kwargs):
    handler=handler or (lambda request:httpx.Response(200,json=response))
    app.state.ai_runtime=Runtime(enabled=True,segmentation=config(points=True,boxes=True),recommendation=config(),transport=httpx.MockTransport(handler),**kwargs)

def image():
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(64,48)).save(out,format='PNG');return out.getvalue()

def segment(client, query=''):
    return client.post('/api/ai/segment'+query,content=image(),headers={'content-type':'image/png'})

def mask():
    return {'masks':[{'geometry':{'type':'Polygon','coordinates':[[[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.1,.1]]]},'confidence':.8}]}

def recommendation_body():
    return {'width_mm':10,'height_mm':10,'material_mm':{'type':'Polygon','coordinates':[[[0,0],[10,0],[10,10],[0,10],[0,0]]]}}

def test_disabled_and_secret_free_availability(client):
    assert client.get('/api/ai/availability').json()['ai_enabled'] is False
    assert segment(client).status_code==503
    assert TOKEN not in client.get('/api/ai/availability').text
    assert client.get('/health').status_code==200

@pytest.mark.parametrize('change,reason',[({'token':''},'credentials_missing'),({'endpoint':''},'configuration_missing'),({'auth':''},'auth_mode_required'),({'provider':'other'},'unsupported_provider')])
def test_missing_configuration_never_calls_provider(client,change,reason):
    c=config()
    for k,v in change.items():setattr(c,k,v)
    app.state.ai_runtime=Runtime(enabled=True,segmentation=c,transport=httpx.MockTransport(lambda _:pytest.fail('Must not call provider')))
    r=segment(client);assert r.status_code==503 and r.json()['detail']==reason

@pytest.mark.parametrize('status,code',[(401,'provider_authentication_failed'),(403,'provider_authentication_failed'),(500,'provider_unavailable')])
def test_auth_and_provider_failure_sanitized_no_retry(client,status,code):
    calls=[]
    def handler(req):calls.append(req);return httpx.Response(status,text=TOKEN)
    install(handler=handler)
    r=segment(client);assert r.status_code==502 and r.json()['detail']==code
    assert TOKEN not in r.text and len(calls)==1

def test_timeout(client):
    install(handler=lambda _: (_ for _ in ()).throw(httpx.ReadTimeout('secret URL')))
    assert segment(client).status_code==504

def test_valid_segmentation_prompts_and_provenance(client):
    pytest.importorskip('shapely')
    def handler(req):
        body=json.loads(req.content);assert body['prompts']['points']==[[.5,.5,1]]
        assert req.headers['authorization']=='Bearer '+TOKEN
        return httpx.Response(200,json=mask())
    install(handler=handler)
    r=segment(client,'?prompts='+__import__('urllib.parse',fromlist=['quote']).quote(json.dumps({'points':[[.5,.5,1]]})))
    assert r.status_code==200,r.text
    assert r.json()['status']=='live_ai' and r.json()['width_px']==64
    assert r.json()['provenance']['source']=='provider_prediction'

@pytest.mark.parametrize('data',[{'masks':[]},{'masks':[{'geometry':{'type':'Polygon','coordinates':[[[0,0],[2,0],[0,1],[0,0]]]}}]}, {'masks':[{'geometry':{'type':'Polygon','coordinates':[[[0,0],[1,1],[0,1],[1,0],[0,0]]]}}]}])
def test_invalid_masks(client,data):
    pytest.importorskip('shapely');install(data)
    assert segment(client).status_code==502

def test_image_and_prompt_validation(client):
    install(mask())
    assert client.post('/api/ai/segment',content=b'not png',headers={'content-type':'image/png'}).status_code==422
    assert client.post('/api/ai/segment',content=b'<svg/>',headers={'content-type':'image/svg+xml'}).status_code==415
    assert segment(client,'?prompts=invalid').status_code==422
    app.state.ai_runtime.segmentation.points=False
    assert segment(client,'?prompts=%7B%22points%22%3A%5B%5B0.5%2C0.5%2C1%5D%5D%7D').status_code==422

def test_body_limit(client):
    assert client.post('/api/ai/recommend',content=b'x'*(8*1024*1024+1)).status_code==413

def test_malformed_transport_output(client):
    install(handler=lambda _:httpx.Response(200,text='not JSON '+TOKEN))
    r=segment(client);assert r.status_code==502 and TOKEN not in r.text

def test_disabled_recommendation_is_explicit_geometry_fallback(client):
    pytest.importorskip('shapely')
    r=client.post('/api/ai/recommend',json=recommendation_body())
    assert r.status_code==200 and r.json()['status']=='deterministic_fallback'
    assert r.json()['provenance'] is None and len(r.json()['ranked_projects'])==3

@pytest.mark.parametrize('ranking',[[{'project_id':'invented','explanation':'bad'}],[{'project_id':'square-tabs','explanation':''}],[],[{'project_id':'square-tabs','explanation':'a'}]*2])
def test_invalid_rankings(client,ranking):
    pytest.importorskip('shapely');install({'ranked_projects':ranking})
    assert client.post('/api/ai/recommend',json=recommendation_body()).status_code==502

def test_infeasible_recommendations_cannot_override_geometry(client):
    pytest.importorskip('shapely')
    install({'ranked_projects':[{'project_id':'corner-pieces','explanation':'AI says yes'}]})
    body={'width_mm':2,'height_mm':2,'clearance_mm':0,'material_mm':{'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}}
    # Triangle markers may fit; the L-shaped project cannot and must be rejected.
    r=client.post('/api/ai/recommend',json=body)
    assert (r.status_code==502) or (r.json()['status']=='deterministic_fallback' and not r.json()['ranked_projects'])

def test_baseten_openai_and_verified_ranking(client):
    pytest.importorskip('shapely')
    def handler(req):
        assert 'messages' in json.loads(req.content)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'ranked_projects':[{'project_id':'square-tabs','explanation':'Two simple pieces.'}]})}}]})
    install(handler=handler);app.state.ai_runtime.recommendation=config('baseten')
    r=client.post('/api/ai/recommend',json=recommendation_body())
    assert r.status_code==200 and r.json()['status']=='live_ai'
    assert r.json()['provenance']['provider']=='baseten'

def test_concurrency_and_cancellation_release_slots():
    async def run():
        started=asyncio.Event()
        async def handler(_):started.set();await asyncio.Event().wait()
        r=Runtime(enabled=True,segmentation=config(),transport=httpx.MockTransport(handler),concurrency=1)
        task=asyncio.create_task(r.call('segmentation',b'x','image/png',{}));await started.wait()
        with pytest.raises(ProviderError,match='inference_busy'):await r.call('segmentation',b'x','image/png',{})
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not r.limit.locked()
    asyncio.run(run())

def test_manual_workflow_still_available(client):
    pytest.importorskip('shapely')
    r=client.post('/api/layouts',json={});assert r.status_code==200 and r.json()['status']=='success'

def test_malformed_chat_content(client):
    pytest.importorskip('shapely')
    install({'choices':[{'message':{'content':'not valid JSON'}}]})
    app.state.ai_runtime.recommendation=config('baseten')
    assert client.post('/api/ai/recommend',json=recommendation_body()).status_code==502

@pytest.mark.parametrize('confidence',[-.1,2,'high'])
def test_invalid_confidence(client,confidence):
    pytest.importorskip('shapely')
    data=mask();data['masks'][0]['confidence']=confidence;install(data)
    assert segment(client).status_code==502

def test_wall_clock_timeout_releases_slot():
    async def run():
        async def slow(_): await asyncio.sleep(1);return httpx.Response(200,json=mask())
        r=Runtime(enabled=True,segmentation=config(),transport=httpx.MockTransport(slow),timeout=.01,concurrency=1)
        with pytest.raises(ProviderError,match='provider_timeout'):await r.call('segmentation',b'x','image/png',{})
        assert not r.limit.locked()
    asyncio.run(run())

def test_optional_cache_is_bounded_and_disabled_by_default():
    async def run():
        calls=[]
        def handler(req):calls.append(req);return httpx.Response(200,json=mask())
        r=Runtime(enabled=True,segmentation=config(),transport=httpx.MockTransport(handler),cache_ttl=10)
        await r.call('segmentation',b'x','image/png',{})
        await r.call('segmentation',b'x','image/png',{})
        assert len(calls)==1
        assert TOKEN not in repr(r.cache)
        r.enabled=False
        with pytest.raises(ProviderError):await r.call('segmentation',b'x','image/png',{})
    asyncio.run(run())
