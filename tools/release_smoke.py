"""Real deterministic release smoke. No AI calls. HTTP by default; --asgi is explicit."""
import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx


def smoke(client):
    for path in ('/health','/ready'):
        response=client.get(path);assert response.status_code==200,(path,response.status_code,response.text)
    availability=client.get('/api/ai/availability').json()
    assert availability['ai_enabled'] is False,'Smoke expects AI_ENABLED=false; never invokes inference'
    index=client.get('/');assert index.status_code==200 and 'text/html' in index.headers['content-type']
    scripts=re.findall(r'<script[^>]*src="([^"]+)"',index.text)
    assert scripts,'Production JS bundle missing'
    for src in scripts:
        response=client.get(src);assert response.status_code==200 and 'javascript' in response.headers['content-type']
    assert client.get('/workspace/outline',headers={'Accept':'text/html'}).status_code==200
    assert client.get('/api/not-a-route',headers={'Accept':'text/html'}).status_code==404
    all_scenes=client.get('/api/demo-scenes').json()
    assert all(s['kind']=='photograph' and s['annotation_source']=='manual_required' for s in all_scenes)
    assert not any(s['id'].startswith(('scene-','ctvg-')) for s in all_scenes)
    assert not any(s.get('polygon_px') or s.get('mask') or s.get('geometry_px') for s in all_scenes)
    scenes=[client.get(f'/api/demo-scenes/scene-{i:02}').json() for i in range(1,13)]
    assert len(scenes)==12
    for scene in scenes:
        assert 'synthetic' in scene['source']
        for field in ('image','mask'):
            r=client.get(scene[field]);assert r.status_code==200;assert ET.fromstring(r.text).tag.endswith('svg')
    projects=client.get('/api/project-templates').json();assert len(projects)>=3
    # Coordinates from a browser-local 400x280 raster, manually traced and
    # calibrated to 80 mm / 320 px. No photo upload is needed for manual tracing.
    material={'type':'Polygon','coordinates':[[[10,10],[90,10],[90,60],[10,60],[10,10]]]}
    for source in ({'scene_id':scenes[0]['id']},{'material_mm':material}):
        body={**source,'template_id':projects[0]['id'],'clearance_mm':.5,'grid_mm':1.2}
        r=client.post('/api/layouts',json=body);assert r.status_code==200,r.text
        assert r.json()['status']=='success' and r.json()['verification']['valid'],r.text
        r=client.post('/api/layouts/svg',json=body);assert r.status_code==200,r.text
        svg=ET.fromstring(r.text)
        assert svg.attrib['width'].endswith('mm') and svg.attrib['height'].endswith('mm')
        if 'material_mm' in source:assert float(svg.attrib['width'][:-2])==80
    fallback=client.post('/api/ai/recommend',json={'width_mm':80,'height_mm':50,'material_mm':material,'clearance_mm':.5,'grid_mm':1.2})
    assert fallback.status_code==200,fallback.text
    assert fallback.json()['status']=='deterministic_fallback' and fallback.json()['provenance'] is None
    assert {p['project_id'] for p in fallback.json()['ranked_projects']}.issubset({p['id'] for p in projects})
    assert fallback.json()['ranked_projects'],'Expected verified manual geometry fits'
    challenge={'scene_id':'scene-06','template_id':'square-tabs','clearance_mm':.5,'grid_mm':.5}
    incomplete=client.post('/api/layouts',json=challenge)
    assert incomplete.status_code==200 and incomplete.json()['status']=='incomplete'
    assert not incomplete.json()['verification']['valid'] and not incomplete.json()['placements']
    assert client.post('/api/layouts/svg',json=challenge).status_code==422
    # A genuine regression photograph goes through the same raw-image endpoint
    # as ordinary upload. No dataset mask or outline is supplied to detection.
    photograph=client.get('/ctvg/ctvg-01.jpeg');assert photograph.status_code==200
    detected=client.post('/api/ai/detect-material?use_ai=false',content=photograph.content,headers={'Content-Type':'image/jpeg'})
    assert detected.status_code==200,detected.text
    detected=detected.json()
    assert not detected['provenance']['ai_image_understanding'] and detected['requires_confirmation']
    ring=detected['geometry_px']['coordinates'][0]
    # TEST measurement supplied by a simulated user; not the source's actual scale.
    ratio=120/(max(p[0] for p in ring)-min(p[0] for p in ring))
    pixels={'type':'Polygon','coordinates':[[[x*ratio,y*ratio] for x,y in ring]]}
    rectangle={'type':'Polygon','coordinates':[[[0,0],[20,0],[20,15],[0,15],[0,0]]]}
    body={'template_id':'custom-rectangles','material_mm':pixels,'parts_mm':[rectangle]*4,
          'clearance_mm':1,'grid_mm':4,'scene_scale_mode':'user_calibrated','source_scene_id':'ctvg-01'}
    fitted=client.post('/api/layouts',json=body);assert fitted.status_code==200,fitted.text
    assert fitted.json()['status']=='success' and fitted.json()['verification']['valid']
    exported=client.post('/api/layouts/svg',json=body);assert exported.status_code==200,exported.text
    assert ET.fromstring(exported.text).attrib['width'].endswith('mm') and 'CC BY 4.0' in exported.text
    for photo_scene in [client.get(f'/api/demo-scenes/ctvg-{i:02}').json() for i in range(1,5)]:
        response=client.get(photo_scene['image']);assert response.status_code==200 and 'image/jpeg' in response.headers['content-type']
        assert client.get(photo_scene['thumbnail']).status_code==200
        assert client.post('/api/layouts',json={'scene_id':photo_scene['id']}).status_code==422
        body={'scene_id':photo_scene['id'],'scene_mm_per_pixel':photo_scene['illustrative_mm_per_pixel'],'scene_scale_mode':'illustrative'}
        result=client.post('/api/layouts',json=body)
        assert result.status_code==200 and result.json()['verification']['valid']
        assert not result.json()['physically_calibrated']
        svg=client.post('/api/layouts/svg',json=body)
        assert svg.status_code==200 and 'ILLUSTRATIVE SCALE ONLY' in svg.text and 'CC BY 4.0' in svg.text
    print('PASS: upload-first empty gallery, health/readiness, production assets, real regression photograph -> pixel contour -> test calibration -> 4 rectangles -> attributed mm SVG, legacy geometry regressions and infeasible export refusal. No inference or browser calls.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8000');p.add_argument('--asgi',action='store_true');args=p.parse_args()
    if args.asgi:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
        from fastapi.testclient import TestClient
        from app.main import app
        app.state.require_frontend=True
        print('Transport: in-process ASGI, not a listening server or browser')
        with TestClient(app) as client:smoke(client)
    else:
        print('Transport: real HTTP to '+args.url)
        with httpx.Client(base_url=args.url,timeout=45,follow_redirects=False,trust_env=False) as client:smoke(client)
