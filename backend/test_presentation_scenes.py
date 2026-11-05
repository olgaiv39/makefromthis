"""Real scene/mask/layout API checks for the hackathon presentation fixtures."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
pytest.importorskip('shapely')
from shapely.geometry import shape, Polygon
from shapely.affinity import scale
from fastapi.testclient import TestClient
from app.main import app
from app.geometry import mask_to_mm
from app.nesting import verify

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('scene_id',[f'scene-{i:02}' for i in range(1,7)])
def test_presentation_scene_api_fits_and_independent_verification(scene_id):
    with TestClient(app) as c:
        scene=c.get('/api/demo-scenes/'+scene_id).json()
        px=shape(scene['geometry_px'])
        assert px.is_valid and px.area>0
        assert px.bounds[2]-px.bounds[0]>.8*scene['width_px']
        assert px.bounds[3]-px.bounds[1]>.7*scene['height_px']
        material=mask_to_mm(ROOT/'public'/scene['mask'].lstrip('/'),scene['mm_per_pixel'])
        assert material.equals(scale(px,xfact=scene['mm_per_pixel'],yfact=scene['mm_per_pixel'],origin=(0,0)))
        geometry_response=c.get('/api/demo-scenes/'+scene_id+'/material')
        assert geometry_response.status_code==200
        assert shape(geometry_response.json()['geometry']).equals(material)
        for project in c.get('/api/project-templates').json():
            body={'scene_id':scene_id,'template_id':project['id'],'clearance_mm':.5,'grid_mm':.5}
            response=c.post('/api/layouts',json=body);assert response.status_code==200,response.text
            result=response.json()
            if scene_id=='scene-06':
                assert material.buffer(-.5).is_empty  # independent geometric infeasibility certificate
                assert result['status']=='incomplete' and not result['verification']['valid']
                assert not result['placements']
                assert c.post('/api/layouts/svg',json=body).status_code==422
                continue
            assert result['status']=='success' and result['verification']['valid'],response.text
            expected={f'part-{i+1:02}':shape(g) for i,g in enumerate(project['parts'])}
            placements=[{**p,'geometry':shape(p['geometry'])} for p in result['placements']]
            assert verify(material,expected,placements,.5)['valid']
            assert result['utilization_percent']==pytest.approx(sum(p.area for p in expected.values())/material.area*100)
            exported=c.post('/api/layouts/svg',json=body)
            assert exported.status_code==200
            svg=ET.fromstring(exported.text)
            assert float(svg.attrib['width'][:-2])==pytest.approx(material.bounds[2]-material.bounds[0])
            assert svg.attrib['height'].endswith('mm')


def test_holes_and_disconnected_topology_are_explicit_and_not_flattened():
    scenes=[s for s in json.loads((ROOT/'backend/app/scenes.json').read_text()) if s['id'].startswith('scene-')]
    multiple=shape(scenes[2]['geometry_px']);cutout=shape(scenes[3]['geometry_px'])
    assert multiple.geom_type=='MultiPolygon' and len(multiple.geoms)==3
    assert cutout.geom_type=='Polygon' and len(cutout.interiors)==1
    # Legacy ring is retained, but cannot stand in for full usable geometry.
    assert multiple.area!=Polygon(scenes[2]['polygon_px']).area
    assert cutout.area<Polygon(scenes[3]['polygon_px']).area


def test_regression_order_and_challenge_label_remain_outside_public_gallery():
    scenes=[s for s in json.loads((ROOT/'backend/app/scenes.json').read_text()) if s['id'].startswith('scene-')]
    assert not any(s['id'].startswith('scene-') for s in TestClient(app).get('/api/demo-scenes').json())
    assert len(scenes)==12
    assert [s['id'] for s in scenes[:6]]==[f'scene-{i:02}' for i in range(1,7)]
    assert all(s['featured'] for s in scenes[:6]) and not any(s['featured'] for s in scenes[6:])
    assert scenes[5]['expected_fit']=='infeasible_at_default_clearance'
    assert '0.72 mm' in scenes[5]['description']
    assert len({s['title'] for s in scenes})==12
