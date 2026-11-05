"""Stage 02 contract tests; all lengths are millimeters."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
pytest.importorskip('shapely', reason='Stage 02 requires the Shapely dependency')
from shapely.geometry import Polygon, MultiPolygon, box, mapping, shape
from app.geometry import mask_to_mm, valid_material
from app.nesting import nest, verify, svg_layout, oriented
from app.layout_api import LayoutRequest, calculate, TEMPLATES
from fastapi.testclient import TestClient
from app.main import app


def placement(key, geom, x=0, y=0, angle=0):
    return dict(id=key, geometry=geom, x_mm=x, y_mm=y, rotation_deg=angle)


def test_valid_placement_and_utilization():
    result = nest(box(0,0,10,10), {'a':box(0,0,2,2), 'b':box(0,0,2,2)}, 0.5, 0.5)
    assert result['status']=='success' and result['verification']['valid']
    assert result['utilization_percent']==pytest.approx(8)
    assert result['placed_area_mm2']==8


def test_insufficient_material_is_not_success():
    r=nest(box(0,0,2,2), {'a':box(0,0,3,3)},0,1)
    assert r['status']=='incomplete' and r['verification']['missing_parts']==['a']
    with pytest.raises(ValueError): svg_layout(r)


def test_concave_material():
    material=Polygon([(0,0),(8,0),(8,2),(2,2),(2,8),(0,8)])
    r=nest(material, {'a':box(0,0,1,4),'b':box(0,0,4,1)},.25,.25)
    assert r['status']=='success'
    assert all(material.covers(shape(p['geometry'])) for p in r['placements'])


def test_holes_and_disconnected_regions(tmp_path):
    mask=tmp_path/'mask.svg'
    mask.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="30" height="20"><rect width="30" height="20" fill="black"/><rect width="10" height="10" fill="white"/><rect x="2" y="2" width="6" height="6" fill="black"/><rect x="20" width="5" height="5" fill="white"/></svg>')
    m=mask_to_mm(mask, .5)
    assert m.geom_type=='MultiPolygon' and len(m.geoms)==2
    assert sum(len(p.interiors) for p in m.geoms)==1
    assert m.area==pytest.approx((100-36+25)*.25)
    r=nest(m,{'a':box(0,0,1.5,1.5)},.25,.25)
    assert r['status']=='success'
    assert m.covers(shape(r['placements'][0]['geometry']))


def test_disconnected_material_places_in_both_regions():
    m=MultiPolygon([box(0,0,3,3),box(5,0,8,3)])
    r=nest(m,{'a':box(0,0,2,2),'b':box(0,0,2,2)},.5,.5)
    assert r['status']=='success'
    assert r['placements'][1]['x_mm']>=5


def test_reject_overlap_independently():
    part=box(0,0,2,2)
    check=verify(box(0,0,10,10),{'a':part,'b':part},[placement('a',part),placement('b',part)],0)
    assert not check['valid'] and any('Overlapping' in s for s in check['errors'])


def test_reject_hole_and_outside():
    material=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(2,2),(5,2),(5,5),(2,5)]])
    for p in [box(3,3,4,4),box(-1,0,0,1)]:
        x,y,_,_=p.bounds
        check=verify(material,{'a':box(0,0,1,1)},[placement('a',p,x,y)],0)
        assert not check['valid'] and any('outside' in s for s in check['errors'])


def test_cutting_clearance_boundary_and_pair():
    part=box(0,0,2,2)
    assert not verify(box(0,0,10,10),{'a':part},[placement('a',part)],.1)['valid']
    from shapely.affinity import translate
    placements=[placement('a',translate(part,1,1),1,1),placement('b',translate(part,3.4,1),3.4,1)]
    check=verify(box(0,0,10,10),{'a':part,'b':part},placements,.5)
    assert not check['valid'] and any('Part clearance' in s for s in check['errors'])
    placements[1]=placement('b',translate(part,3.5,1),3.5,1)
    assert verify(box(0,0,10,10),{'a':part,'b':part},placements,.5)['valid']


def test_rotations():
    p=box(0,0,4,2)
    r=nest(box(0,0,2,4), {'a':p}, 0, 1)
    assert r['status']=='success' and r['placements'][0]['rotation_deg']==90
    for angle in [0,90,180,270]:
        g=oriented(p,angle)
        assert verify(box(0,0,10,10),{'a':p},[placement('a',g,angle=angle)],0)['valid']


def test_deterministic():
    args=(box(0,0,10,10),{'b':box(0,0,2,2),'a':box(0,0,3,1)},.5,.5)
    assert json.dumps(nest(*args),sort_keys=True)==json.dumps(nest(*args),sort_keys=True)


def test_svg_physical_dimensions_and_holes():
    m=Polygon([(5,10),(25,10),(25,40),(5,40)],holes=[[(15,20),(20,20),(20,25),(15,25)]])
    r=nest(m,{'a':box(0,0,2,2)},.5,1)
    svg=ET.fromstring(svg_layout(r))
    assert svg.attrib['width']=='20mm' and svg.attrib['height']=='30mm'
    assert svg.attrib['viewBox']=='5 10 20 30'
    paths=svg.findall('{http://www.w3.org/2000/svg}path')
    assert paths[0].attrib['fill-rule']=='evenodd' and paths[0].attrib['d'].count('M')==2
    assert len(paths)==2


def test_invalid_geometry_and_budget():
    with pytest.raises(ValueError): valid_material(Polygon([(0,0),(2,2),(0,2),(2,0)]))
    with pytest.raises(ValueError): nest(box(0,0,100,100),{'a':box(0,0,1,1)},0,.001)
    with pytest.raises(ValueError): nest(box(0,0,10,10),{'a':box(0,0,1,1)},-1,1)


def test_mask_unsupported_constructs_fail_closed(tmp_path):
    p=tmp_path/'mask.svg'
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path fill="white" d="M0 0L10 0L10 10Z"/></svg>')
    with pytest.raises(ValueError): mask_to_mm(p,1)


def test_all_existing_scene_scales_and_templates():
    root=Path(__file__).resolve().parents[1]
    scenes=json.loads((root/'backend/app/scenes.json').read_text())
    for s in [s for s in scenes if s['id'].startswith('scene-')]:
        material=mask_to_mm(root/'public'/s['mask'].lstrip('/'),s['mm_per_pixel'])
        assert material.area==pytest.approx(shape(s['geometry_px']).area*s['mm_per_pixel']**2)
    for template_id in TEMPLATES:
        r=calculate(LayoutRequest(template_id=template_id))
        assert r['status']=='success'


def test_endpoints():
    c=TestClient(app)
    assert len(c.get('/api/project-templates').json())>=3
    assert c.get('/api/demo-scenes/scene-01/material').json()['units']=='mm'
    assert c.get('/api/demo-scenes/missing/material').status_code==404
    r=c.post('/api/layouts',json={})
    assert r.status_code==200 and r.json()['status']=='success'
    svg=c.post('/api/layouts/svg',json={})
    assert svg.status_code==200 and 'image/svg+xml' in svg.headers['content-type']
    assert ET.fromstring(svg.text).attrib['width'].endswith('mm')
    assert c.post('/api/layouts',json={'clearance_mm':-1}).status_code==422
    assert c.post('/api/layouts',json={'template_id':'missing'}).status_code==404
    bad={'material_mm':mapping(box(0,0,1,1)), 'parts_mm':[mapping(box(0,0,2,2))]}
    assert c.post('/api/layouts',json=bad).json()['status']=='incomplete'
    assert c.post('/api/layouts/svg',json=bad).status_code==422


def test_verifier_rejects_changed_shapes_and_duplicate_ids():
    expected={'a':box(0,0,2,2)}
    changed=verify(box(0,0,10,10),expected,[placement('a',box(0,0,1,1))],0)
    assert not changed['valid'] and any('shape differs' in s for s in changed['errors'])
    duplicate=verify(box(0,0,10,10),expected,[placement('a',expected['a'])]*2,0)
    assert not duplicate['valid']
