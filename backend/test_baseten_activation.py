"""Stage 04B TEST DOUBLES ONLY. No live inference or real account credentials."""
import asyncio
import importlib.util
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.providers.core import Config, Runtime, MetaRecommendations, ProviderError
from app.providers.baseten import CHAT_ENDPOINT, HACKATHON_MODEL

TEST_KEY='TEST_ONLY_BASETEN_KEY_NOT_A_CREDENTIAL'


def configured_env(monkeypatch):
    monkeypatch.setenv('RECOMMENDATION_PROVIDER','baseten')
    monkeypatch.setenv('BASETEN_API_KEY',TEST_KEY)
    monkeypatch.delenv('RECOMMENDATION_ENDPOINT_URL',raising=False)
    monkeypatch.delenv('RECOMMENDATION_MODEL_ID',raising=False)
    monkeypatch.setenv('RECOMMENDATION_AUTH_TOKEN','TEST_ONLY_WRONG_LEGACY_TOKEN')


def test_baseten_env_selects_exact_hackathon_and_key(monkeypatch):
    configured_env(monkeypatch)
    c=Config.env('RECOMMENDATION')
    assert c.endpoint==CHAT_ENDPOINT and c.model==HACKATHON_MODEL
    assert c.token==TEST_KEY and c.headers()=={'Authorization':'Bearer '+TEST_KEY}
    assert TEST_KEY not in repr(c)
    assert not c.problem('recommendation')


def test_missing_baseten_key_does_not_use_legacy_token(monkeypatch):
    configured_env(monkeypatch);monkeypatch.delenv('BASETEN_API_KEY')
    assert Config.env('RECOMMENDATION').problem('recommendation')=='credentials_missing'


def test_legacy_muse_slug_is_rejected(monkeypatch):
    configured_env(monkeypatch);monkeypatch.setenv('RECOMMENDATION_MODEL_ID','meta-models/muse-spark-open')
    assert Config.env('RECOMMENDATION').problem('recommendation')=='hackathon_model_required'


def test_baseten_key_not_reused_for_modal(monkeypatch):
    configured_env(monkeypatch);monkeypatch.setenv('RECOMMENDATION_PROVIDER','modal')
    assert Config.env('RECOMMENDATION').token=='TEST_ONLY_WRONG_LEGACY_TOKEN'


def test_schema_ids_token_budget_and_reasoning_are_bounded(monkeypatch):
    configured_env(monkeypatch);c=Config.env('RECOMMENDATION')
    payload=MetaRecommendations(c).chat_payload({'verified_templates':[{'project_id':'square-tabs'}]})
    schema=payload['response_format']['json_schema']['schema']
    assert schema['properties']['ranked_projects']['items']['properties']['project_id']['enum']==['square-tabs']
    assert payload['model']==HACKATHON_MODEL and payload['max_tokens']==512
    assert payload['reasoning_effort']=='low'
    assert payload['temperature']==1.0 and 'top_p' not in payload
    assert payload['response_format']['json_schema']['strict'] is True
    assert schema['additionalProperties'] is False
    assert TEST_KEY not in json.dumps(payload)


def envelope(content,**extra):
    return {'model':HACKATHON_MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content),'reasoning_content':'TEST_ONLY_PRIVATE_REASONING'}}],
            'usage':{'prompt_tokens':12,'completion_tokens':24,'total_tokens':36},**extra}


def test_existing_ui_endpoint_uses_exact_profile_and_real_geometry_checks(monkeypatch):
    pytest.importorskip('shapely');configured_env(monkeypatch)
    calls=[]
    def handler(request):
        calls.append(request)
        assert str(request.url)==CHAT_ENDPOINT
        assert request.headers['Authorization']=='Bearer '+TEST_KEY
        assert json.loads(request.content)['model']==HACKATHON_MODEL
        return httpx.Response(200,json=envelope({'ranked_projects':[{'project_id':'square-tabs','explanation':'Simple usable tabs.'}]}))
    monkeypatch.setattr(app.state,'ai_runtime',Runtime(enabled=True,transport=httpx.MockTransport(handler)))
    body={'width_mm':10,'height_mm':10,'material_mm':{'type':'Polygon','coordinates':[[[0,0],[10,0],[10,10],[0,10],[0,0]]]}}
    with TestClient(app) as c:
        r=c.post('/api/ai/recommend',json=body)
        assert r.status_code==200 and r.json()['status']=='live_ai'
        assert r.json()['provenance']=={'provider':'baseten','model_id':HACKATHON_MODEL}
        assert TEST_KEY not in r.text and 'PRIVATE_REASONING' not in r.text
    assert len(calls)==1

@pytest.mark.parametrize('kind',['length','refusal','wrong_model','missing_content'])
def test_incomplete_refused_or_substituted_outputs_fail_without_retry(kind):
    response=envelope({'ranked_projects':[]})
    if kind=='length':response['choices'][0]['finish_reason']='length'
    elif kind=='refusal':response['choices'][0]['message']['refusal']='TEST_ONLY_REFUSAL'
    elif kind=='wrong_model':response['model']='meta-models/muse-spark-open'
    else:response['choices'][0]['message']['content']=None
    calls=[]
    def handler(req):calls.append(req);return httpx.Response(200,json=response)
    adapter=MetaRecommendations(Config(provider='baseten',model=HACKATHON_MODEL,endpoint=CHAT_ENDPOINT,token=TEST_KEY),transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError):asyncio.run(adapter.recommend({}))
    assert len(calls)==1
    assert adapter.metrics['http_status']==200 and adapter.metrics['token_usage']['total_tokens']==36
    assert TEST_KEY not in json.dumps(adapter.metrics) and 'PRIVATE_REASONING' not in json.dumps(adapter.metrics)


def smoke_module():
    path=Path(__file__).resolve().parents[1]/'tools/baseten_live_smoke.py'
    spec=importlib.util.spec_from_file_location('baseten_smoke_test_only',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_live_smoke_default_and_missing_key_make_zero_requests():
    module=smoke_module()
    transport=httpx.MockTransport(lambda _:pytest.fail('Gated smoke must not use transport'))
    for env in ({'BASETEN_API_KEY':TEST_KEY},{'LIVE_AI_TEST':'1'}):
        report=asyncio.run(module.run(env,transport))
        assert report['status']=='blocked' and report['inference_requests']==0


def test_live_smoke_is_one_small_post_after_billing_get():
    pytest.importorskip('shapely');module=smoke_module();calls=[]
    def handler(request):
        calls.append(request)
        if request.method=='GET':return httpx.Response(403,text='TEST_ONLY_BILLING_UNAVAILABLE')
        payload=json.loads(request.content)
        assert payload['model']==HACKATHON_MODEL and payload['max_tokens']==1024
        assert payload['reasoning_effort']=='low' and payload['temperature']==1.0
        return httpx.Response(200,json=envelope({'ranked_projects':[{'project_id':'square-tabs','explanation':'Two simple pieces.'}]}))
    report=asyncio.run(module.run({'LIVE_AI_TEST':'1','BASETEN_API_KEY':TEST_KEY},httpx.MockTransport(handler)))
    assert [c.method for c in calls]==['GET','POST']
    assert report['status']=='passed' and report['http_status']==200
    assert report['billing']['http_status']==403
    assert report['billing']['credit_confirmation']=='unconfirmed'
    assert report['token_usage']['total_tokens']==36 and report['latency_ms']>=0
    assert report['finish_reason']=='stop' and report['visible_content_present'] is True
    assert report['completion_tokens']==24
    assert 'PRIVATE_REASONING' not in json.dumps(report) and TEST_KEY not in json.dumps(report)


def test_usage_http_200_is_not_credit_confirmation():
    module=smoke_module()
    report=asyncio.run(module.check_billing(TEST_KEY,httpx.MockTransport(lambda _:httpx.Response(200,json={'credits_used':0}))))
    assert report['http_status']==200 and report['credit_confirmation']=='unconfirmed' and report['remaining_credit'] is None


def test_live_smoke_failure_does_not_retry():
    pytest.importorskip('shapely');module=smoke_module();calls=[]
    def handler(req):calls.append(req);return httpx.Response(401,text=TEST_KEY)
    report=asyncio.run(module.run({'LIVE_AI_TEST':'1','BASETEN_API_KEY':TEST_KEY},httpx.MockTransport(handler)))
    assert [c.method for c in calls]==['GET','POST']
    assert report['status']=='failed' and report['http_status']==401
    assert report['live_inference_performed'] is False
    assert TEST_KEY not in json.dumps(report)

@pytest.mark.parametrize('override',[
    {'RECOMMENDATION_MODEL_ID':'meta-models/muse-spark-open'},
    {'RECOMMENDATION_ENDPOINT_URL':'https://other.invalid/chat/completions'},
])
def test_live_smoke_never_substitutes_model_or_destination(override):
    report=asyncio.run(smoke_module().run({'LIVE_AI_TEST':'1','BASETEN_API_KEY':TEST_KEY,**override},
        httpx.MockTransport(lambda _:pytest.fail('Must not call a mismatched destination/model'))))
    assert report['status']=='blocked' and report['inference_requests']==0


@pytest.mark.parametrize('finish,content,error',[
    ('length', '{"ranked_projects":[', 'incomplete_provider_output'),
    # A plausible complete object is still unsafe if the provider reports truncation.
    ('length', '{"ranked_projects":[]}', 'incomplete_provider_output'),
    ('length', None, 'incomplete_provider_output'),
    ('stop', None, 'malformed_provider_output'),
    ('stop', '', 'malformed_provider_output'),
    ('stop', '   ', 'malformed_provider_output'),
    ('stop', 'TEST_ONLY_INVALID_JSON', 'malformed_provider_output'),
])
def test_chat_failures_retain_safe_completion_telemetry(finish,content,error,capsys,caplog):
    response=envelope({})
    response['choices'][0].update(finish_reason=finish,message={
        'content':content,'reasoning_content':'TEST_ONLY_PRIVATE_REASONING'})
    response['usage']={'prompt_tokens':335,'completion_tokens':256,'total_tokens':591,
                       'completion_tokens_details':{'reasoning_tokens':240,
                                                   'private':'TEST_ONLY_PRIVATE_USAGE'}}
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json=response)
    adapter=MetaRecommendations(Config(provider='baseten',model=HACKATHON_MODEL,
        endpoint=CHAT_ENDPOINT,token=TEST_KEY),transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError,match='^'+error+'$'):
        asyncio.run(adapter.recommend({}))
    assert len(calls)==1
    assert adapter.metrics['http_status']==200 and adapter.metrics['finish_reason']==finish
    assert adapter.metrics['visible_content_present']==bool(content and content.strip())
    assert adapter.metrics['visible_content_length']==(len(content) if content is not None else 0)
    assert adapter.metrics['reasoning_tokens']==240 and adapter.metrics['completion_tokens']==256
    captured=capsys.readouterr()
    safe=json.dumps(adapter.metrics)+captured.out+captured.err+caplog.text
    for private in (TEST_KEY,'TEST_ONLY_PRIVATE_REASONING','TEST_ONLY_PRIVATE_USAGE','TEST_ONLY_INVALID_JSON'):
        assert private not in safe


def test_structured_completion_retains_metrics_without_visible_or_reasoning_text(capsys,caplog):
    ranking={'ranked_projects':[{'project_id':'square-tabs','explanation':'TEST_ONLY_VISIBLE_CONTENT'}]}
    response=envelope(ranking)
    response['usage']['completion_tokens_details']={'reasoning_tokens':17}
    adapter=MetaRecommendations(Config(provider='baseten',model=HACKATHON_MODEL,
        endpoint=CHAT_ENDPOINT,token=TEST_KEY),
        transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response)))
    result=asyncio.run(adapter.recommend({'verified_templates':[{'project_id':'square-tabs'}]}))
    from app.providers.baseten import validate_ranking
    assert validate_ranking(result,['square-tabs'])==ranking['ranked_projects']
    assert adapter.metrics['finish_reason']=='stop'
    assert adapter.metrics['visible_content_present'] is True
    assert adapter.metrics['visible_content_length']==len(json.dumps(ranking))
    assert adapter.metrics['reasoning_tokens']==17 and adapter.metrics['completion_tokens']==24
    captured=capsys.readouterr()
    safe=json.dumps(adapter.metrics)+captured.out+captured.err+caplog.text
    for private in (TEST_KEY,'TEST_ONLY_VISIBLE_CONTENT','TEST_ONLY_PRIVATE_REASONING'):
        assert private not in safe


@pytest.mark.parametrize('value,expected',[(0,0),(7,7),(-1,None),(True,None),('TEST_ONLY_PRIVATE_USAGE',None)])
def test_reasoning_usage_metadata_accepts_only_nonnegative_integers(value,expected):
    response=envelope({'ranked_projects':[]})
    response['usage']['completion_tokens_details']={'reasoning_tokens':value}
    adapter=MetaRecommendations(Config(provider='baseten',model=HACKATHON_MODEL,
        endpoint=CHAT_ENDPOINT,token=TEST_KEY),
        transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response)))
    asyncio.run(adapter.recommend({}))
    assert adapter.metrics['reasoning_tokens']==expected
    assert 'TEST_ONLY_PRIVATE_USAGE' not in json.dumps(adapter.metrics)


def test_unknown_finish_reason_cannot_leak_arbitrary_provider_text():
    response=envelope({})
    response['choices'][0]['finish_reason']='TEST_ONLY_PRIVATE_FINISH_REASON'
    adapter=MetaRecommendations(Config(provider='baseten',model=HACKATHON_MODEL,
        endpoint=CHAT_ENDPOINT,token=TEST_KEY),
        transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response)))
    with pytest.raises(ProviderError,match='incomplete_provider_output'):
        asyncio.run(adapter.recommend({}))
    assert adapter.metrics['finish_reason']=='other'
    assert 'TEST_ONLY_PRIVATE_FINISH_REASON' not in json.dumps(adapter.metrics)


@pytest.mark.parametrize('project_id,width,height',[
    ('TEST_ONLY_UNKNOWN_PROJECT',10,10),
    ('corner-pieces',4,2),
])
def test_baseten_structured_ids_cannot_bypass_actual_feasibility(monkeypatch,project_id,width,height):
    pytest.importorskip('shapely');configured_env(monkeypatch)
    from app.layout_api import calculate, LayoutRequest
    material={'type':'Polygon','coordinates':[[[0,0],[width,0],[width,height],[0,height],[0,0]]]}
    # At least one actual fit is required so fallback cannot mask rejection.
    assert calculate(LayoutRequest(material_mm=material,template_id='square-tabs',clearance_mm=0))['status']=='success'
    if project_id=='corner-pieces':
        assert calculate(LayoutRequest(material_mm=material,template_id=project_id,clearance_mm=0))['status']!='success'
    calls=[]
    def handler(request):
        calls.append(request)
        payload=json.loads(request.content)
        allowed=payload['response_format']['json_schema']['schema']['properties']['ranked_projects']['items']['properties']['project_id']['enum']
        assert project_id not in allowed
        return httpx.Response(200,json=envelope({'ranked_projects':[{'project_id':project_id,'explanation':'TEST_ONLY_INVALID_FIT_CLAIM'}]}))
    monkeypatch.setattr(app.state,'ai_runtime',Runtime(enabled=True,transport=httpx.MockTransport(handler)))
    with TestClient(app) as client:
        response=client.post('/api/ai/recommend',json={'material_mm':material,
            'width_mm':width,'height_mm':height,'clearance_mm':0})
    assert len(calls)==1
    assert response.status_code==502 and response.json()['detail']=='invalid_recommendation_output'
    assert 'TEST_ONLY_INVALID_FIT_CLAIM' not in response.text


def test_live_smoke_reports_truncation_separately_from_billing_failure():
    pytest.importorskip('shapely');module=smoke_module();calls=[]
    def handler(request):
        calls.append(request)
        if request.method=='GET':return httpx.Response(403,text='TEST_ONLY_PRIVATE_BILLING')
        response=envelope({})
        response['choices'][0].update(finish_reason='length',message={
            'content':None,'reasoning_content':'TEST_ONLY_PRIVATE_REASONING'})
        response['usage']={'completion_tokens':1024,'completion_tokens_details':{'reasoning_tokens':1024}}
        return httpx.Response(200,json=response)
    report=asyncio.run(module.run({'LIVE_AI_TEST':'1','BASETEN_API_KEY':TEST_KEY},httpx.MockTransport(handler)))
    assert [request.method for request in calls]==['GET','POST']
    assert report['inference_requests']==1 and report['http_status']==200
    assert report['billing']['http_status']==403
    assert report['status']=='failed' and report['reason']=='incomplete_provider_output'
    assert report['finish_reason']=='length' and report['visible_content_present'] is False
    assert report['visible_content_length']==0 and report['reasoning_tokens']==1024
    assert report['completion_tokens']==1024
    assert 'TEST_ONLY_PRIVATE' not in json.dumps(report) and TEST_KEY not in json.dumps(report)


def test_missing_geometry_blocks_before_billing_or_inference(monkeypatch):
    module=smoke_module()
    def unavailable():raise ImportError('TEST_ONLY_MISSING_SHAPELY')
    monkeypatch.setattr(module,'verified_context',unavailable)
    transport=httpx.MockTransport(lambda _:pytest.fail('Geometry preflight must precede every HTTP call'))
    report=asyncio.run(module.run({'LIVE_AI_TEST':'1','BASETEN_API_KEY':TEST_KEY},transport))
    assert report['status']=='blocked' and report['reason']=='geometry_unavailable'
    assert report['inference_requests']==0 and report['http_status'] is None
    assert report['billing']['reason']=='not_checked'
