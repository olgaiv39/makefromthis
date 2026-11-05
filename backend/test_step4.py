"""Real-photo Step 4 regression. Provider traffic is explicitly mocked, never live."""
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx
import pytest
from fastapi.testclient import TestClient
from shapely import affinity
from shapely.geometry import box,mapping,shape
from app.main import app
from app.material_detection import decode_photo,detect_outline
from app.nesting import verify
from app.providers.core import Runtime,Config
from app.providers.baseten import CHAT_ENDPOINT,HACKATHON_MODEL

@pytest.fixture(scope='module')
def material():
    source=Path(__file__).resolve().parents[1]/'examples/craft_photos/incoming/Cutting_mat.jpg'
    pixels=shape(detect_outline(decode_photo(source.read_bytes(),'image/jpeg'))['geometry_px'])
    # Operator supplied 70 mm. These are representative visible right-edge clicks,
    # not a claim that the operator's uncaptured click coordinates are identical.
    factor=70/math.dist((745,132),(786,464))
    return affinity.scale(pixels,xfact=factor,yfact=factor,origin=(0,0))

def cutting(g,width=30,height=30,quantity=4,grid=2):
    return {'material_mm':mapping(g),'parts_mm':[mapping(box(0,0,width,height)) for _ in range(quantity)],
            'template_id':'custom-rectangles','scene_scale_mode':'user_calibrated','clearance_mm':.5,'grid_mm':grid}

def ideas(g,width=30,height=30,quantity=4):
    x,y,a,b=g.bounds
    return {'material_mm':mapping(g),'width_mm':a-x,'height_mm':b-y,'material_type':'cotton',
            'preferences':'patchwork squares','piece_width_mm':width,'piece_height_mm':height,
            'quantity':quantity,'clearance_mm':.5,'grid_mm':4.1}

def fake_runtime(handler,enabled=True):
    return Runtime(enabled=enabled,recommendation=Config(provider='baseten',endpoint=CHAT_ENDPOINT,model=HACKATHON_MODEL,
                   token='TEST_ONLY_STEP4_KEY'),transport=httpx.MockTransport(handler))

@pytest.mark.parametrize('width,height,quantity,status',[(30,30,1,'success'),(20,20,4,'success'),
    (30,30,4,'incomplete'),(200,200,4,'incomplete')])
def test_real_photo_layout_counts_verification_and_svg(material,width,height,quantity,status):
    body=cutting(material,width,height,quantity)
    with TestClient(app) as client:
        response=client.post('/api/layouts',json=body);assert response.status_code==200,response.text
        layout=response.json();assert layout['status']==status
        assert len(layout['placements'])+len(layout['verification']['missing_parts'])==quantity
        assert layout['fit_diagnostics']['requested_count']==quantity
        exported=client.post('/api/layouts/svg',json=body)
        if status=='success':
            expected={f'part-{i+1:02}':shape(p) for i,p in enumerate(body['parts_mm'])}
            assert verify(material,expected,[{**p,'geometry':shape(p['geometry'])} for p in layout['placements']],.5)['valid']
            assert exported.status_code==200
            assert ET.fromstring(exported.text).attrib['width'].endswith('mm')
        else:
            assert not layout['verification']['valid'] and exported.status_code==422
            assert layout['fit_diagnostics']['code']==('part_exceeds_material_bounds' if width==200 else 'heuristic_incomplete')

def test_small_calibration_and_invalid_work_budget_are_diagnosed(material):
    tiny=affinity.scale(material,xfact=.05,yfact=.05,origin=(0,0))
    with TestClient(app) as client:
        result=client.post('/api/layouts',json=cutting(tiny)).json()
        assert result['status']=='incomplete' and result['fit_diagnostics']['code']=='part_exceeds_material_bounds'
        rejected=client.post('/api/layouts',json=cutting(material,grid=.001))
        assert rejected.status_code==422 and 'budget' in rejected.json()['detail'].lower()

def test_tight_rectangle_finer_search_succeeds_without_changing_solver():
    with TestClient(app) as client:
        coarse=cutting(box(0,0,40,30),39,29,1,grid=1)
        assert client.post('/api/layouts',json=coarse).json()['fit_diagnostics']['code']=='heuristic_incomplete'
        fine={**coarse,'grid_mm':.5}
        assert client.post('/api/layouts',json=fine).json()['verification']['valid']

def test_oversized_request_still_sends_only_feasible_practical_options_to_muse(material,monkeypatch):
    calls=[]
    def handler(request):
        assert str(request.url)==CHAT_ENDPOINT
        payload=json.loads(request.content);assert payload['model']==HACKATHON_MODEL
        context=json.loads(payload['messages'][1]['content']);options=context['verified_templates'];calls.append(options)
        assert 1<=len(options)<=6
        assert all(o['verified'] and min(o['width_mm'],o['height_mm'])>=5 for o in options)
        assert not any(o['project_id']=='rectangles' for o in options)
        return httpx.Response(200,json={'model':HACKATHON_MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'ranked_projects':[{'project_id':options[0]['project_id'],'explanation':'These smaller cotton squares fit for patchwork.'}]})}}]})
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(handler))
    with TestClient(app) as client:
        result=client.post('/api/ai/cutting-ideas',json=ideas(material,200,200)).json()
        assert result['status']=='live_ai' and len(calls)==1
        assert result['ranked_projects'][0]['project_id']==calls[0][0]['project_id']
        # Every offered option can reproduce its exact complete fit and SVG.
        for option in result['options']:
            request=cutting(material,option['width_mm'],option['height_mm'],option['quantity'],option['grid_mm'])
            fitted=client.post('/api/layouts',json=request)
            assert fitted.status_code==200 and fitted.json()['verification']['valid']
        option=result['options'][0]
        assert client.post('/api/layouts/svg',json=cutting(material,option['width_mm'],option['height_mm'],option['quantity'],option['grid_mm'])).status_code==200

@pytest.mark.parametrize('enabled,use_ai',[(False,True),(True,False)])
def test_explicit_offline_options_do_not_make_inference_requests(material,monkeypatch,enabled,use_ai):
    def forbidden(request):raise AssertionError('No inference permitted')
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(forbidden,enabled))
    with TestClient(app) as client:
        availability=client.get('/api/ai/availability').json()
        assert availability['material_vision']['available'] is enabled
        assert availability['recommendation']['available'] is enabled
        result=client.post('/api/ai/cutting-ideas?use_ai='+str(use_ai).lower(),json=ideas(material,200,200)).json()
        assert result['status']=='deterministic_fallback' and result['options']
        assert result['ranked_projects']==[] and result['provenance'] is None
        assert result['reason']==('ai_disabled' if not enabled else 'geometry_only_requested')

def test_small_material_has_no_miniature_ai_fallback_or_paid_call(monkeypatch):
    def forbidden(request):raise AssertionError('No viable practical options: do not call inference')
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(forbidden))
    with TestClient(app) as client:
        result=client.post('/api/ai/cutting-ideas',json=ideas(box(0,0,4,4))).json()
        assert result['reason']=='no_verified_fits' and not result['options'] and not result['ranked_projects']

def test_bad_calibrated_dimensions_refused_before_model(monkeypatch):
    def forbidden(request):raise AssertionError('Invalid input must not reach provider')
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(forbidden))
    body=ideas(box(0,0,100,80));body['width_mm']=10
    with TestClient(app) as client:
        response=client.post('/api/ai/cutting-ideas',json=body)
        assert response.status_code==422 and response.json()['detail']=='dimensions_must_match_calibrated_geometry'

def test_doll_shirt_receives_diverse_verified_blanks_without_false_garment_claims(monkeypatch):
    g=box(0,0,80,80);calls=[]
    def handler(request):
        assert str(request.url)==CHAT_ENDPOINT
        payload=json.loads(request.content);assert payload['model']==HACKATHON_MODEL
        context=json.loads(payload['messages'][1]['content']);options=context['verified_templates'];calls.append(options)
        assert {o['shape_kind'] for o in options}=={'square_patch','narrow_strip','fabric_panel'}
        assert len(options)==3 and len({tuple(sorted((o['width_mm'],o['height_mm']))) for o in options})==3
        assert 'not a complete garment' in context['project_limitation']
        assert 'Never claim' in context['instruction']
        # Deliberately misleading mocked model prose must never reach the user.
        ranking=[{'project_id':o['project_id'],'explanation':'A perfect fit for a finished doll t-shirt.'} for o in options]
        return httpx.Response(200,json={'model':HACKATHON_MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'ranked_projects':ranking})}}]})
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(handler))
    body=ideas(g,10,10);body['preferences']='a doll t-shirt'
    with TestClient(app) as client:
        response=client.post('/api/ai/cutting-ideas',json=body);assert response.status_code==200,response.text
        result=response.json();assert result['status']=='live_ai' and len(calls)==1
        assert result['explanation_source']=='supported_operation_descriptions'
        assert 'neckline' in result['project_limitation']
        assert not any('perfect fit' in p['explanation'] or 'finished doll' in p['explanation'] for p in result['ranked_projects'])
        assert any(o['width_mm']!=o['height_mm'] for o in result['options'])
        for option in result['options']:
            request=cutting(g,option['width_mm'],option['height_mm'],option['quantity'],option['grid_mm'])
            assert client.post('/api/layouts',json=request).json()['verification']['valid']

def test_offline_candidates_do_not_repeat_identical_sizes_with_different_quantities(monkeypatch):
    def forbidden(request):raise AssertionError('No inference in geometry-only test')
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(forbidden))
    body=ideas(box(0,0,80,80),10,10);body['preferences']='a doll t-shirt'
    with TestClient(app) as client:
        result=client.post('/api/ai/cutting-ideas?use_ai=false',json=body).json()
        assert result['status']=='deterministic_fallback'
        options=result['options'];dimensions=[tuple(sorted((o['width_mm'],o['height_mm']))) for o in options]
        assert len(dimensions)==len(set(dimensions))
        assert {o['shape_kind'] for o in options}=={'square_patch','narrow_strip','fabric_panel'}
        assert result['project_limitation']

def test_unsupported_project_limit_is_returned_even_when_no_blank_fits(monkeypatch):
    def forbidden(request):raise AssertionError('No viable configurations: no inference')
    monkeypatch.setattr(app.state,'ai_runtime',fake_runtime(forbidden))
    body=ideas(box(0,0,4,4),10,10);body['preferences']='doll t-shirt'
    with TestClient(app) as client:
        result=client.post('/api/ai/cutting-ideas',json=body).json()
        assert result['reason']=='no_verified_fits' and result['project_limitation'] and not result['options']
