"""Actual CTVG photographs/annotations, existing API, no provider calls."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
pytest.importorskip('shapely')
from shapely.geometry import Polygon,shape
from shapely.affinity import scale
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.geometry import mask_to_mm
from app.nesting import verify

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('scene_id',[f'ctvg-{i:02}' for i in range(1,5)])
def test_real_photo_annotation_to_verified_svg(scene_id):
    with TestClient(app) as c:
        scene=c.get('/api/demo-scenes/'+scene_id).json()
        assert scene['kind']=='photograph' and scene['annotation_source']=='dataset_ground_truth'
        assert scene['mm_per_pixel'] is None and scene['scale_status']=='uncalibrated'
        assert 'synthetic' not in scene['source'] and 'no AI segmentation' in scene['source']
        provenance=scene['annotation_provenance']
        image=ROOT/'public'/scene['image'].lstrip('/')
        annotation=ROOT/'public'/provenance['annotation_url'].lstrip('/')
        assert hashlib.sha256(image.read_bytes()).hexdigest()==provenance['source_image_sha256']
        assert hashlib.sha256(annotation.read_bytes()).hexdigest()==provenance['source_annotation_sha256']
        raw=json.loads(annotation.read_text())['image']
        assert len(raw['polygons'])==1
        original=Polygon(raw['polygons'][0]['segmentation'])
        assert original.is_valid and len(original.interiors)==0
        assert scene['polygon_px']==raw['polygons'][0]['segmentation']
        assert shape(scene['geometry_px']).equals(original)
        assert scene['geometry_px']['coordinates'][0][:-1]==raw['polygons'][0]['segmentation']
        assert '/real/' in provenance['source_image'] and '/full/' not in provenance['source_image']
        with Image.open(image) as source:assert source.size==(448,448)
        with Image.open(ROOT/'public'/scene['thumbnail'].lstrip('/')) as thumb:assert max(thumb.size)<=224
        material_response=c.get('/api/demo-scenes/'+scene_id+'/material').json()
        assert material_response['units']=='px' and material_response['mm_per_pixel'] is None
        assert material_response['area_px2']==original.area
        assert c.post('/api/layouts',json={'scene_id':scene_id}).status_code==422
        assert c.post('/api/layouts/svg',json={'scene_id':scene_id}).status_code==422
        mm=scene['illustrative_mm_per_pixel']
        material=mask_to_mm(ROOT/'public'/scene['mask'].lstrip('/'),mm)
        assert material.equals(scale(original,xfact=mm,yfact=mm,origin=(0,0)))
        for project in c.get('/api/project-templates').json():
            body={'scene_id':scene_id,'template_id':project['id'],'scene_mm_per_pixel':mm,'scene_scale_mode':'illustrative','grid_mm':.5,'clearance_mm':.5}
            response=c.post('/api/layouts',json=body);assert response.status_code==200,response.text
            layout=response.json();assert layout['status']=='success' and layout['verification']['valid']
            assert layout['scale_status']=='illustrative' and layout['physically_calibrated'] is False
            assert layout['annotation_source']=='dataset_ground_truth'
            expected={f'part-{i+1:02}':shape(p) for i,p in enumerate(project['parts'])}
            placed=[{**p,'geometry':shape(p['geometry'])} for p in layout['placements']]
            assert verify(material,expected,placed,.5)['valid']
            exported=c.post('/api/layouts/svg',json=body);assert exported.status_code==200
            svg=ET.fromstring(exported.text)
            assert svg.attrib['width'].endswith('mm')
            assert 'ILLUSTRATIVE SCALE ONLY' in exported.text and 'CC BY 4.0' in exported.text
            assert provenance['doi'] in exported.text


def test_public_gallery_contains_only_real_photos_and_preserves_private_fixtures():
    data=TestClient(app).get('/api/demo-scenes').json()
    assert data==[]  # CTVG and synthetic imagery are internal regression fixtures only.
    fixtures=json.loads((ROOT/'backend/app/scenes.json').read_text())
    assert len(fixtures)==16
    assert [s['id'] for s in fixtures[4:]]==[f'scene-{i:02}' for i in range(1,13)]
    for entry in fixtures:
        response=TestClient(app).get('/api/demo-scenes/'+entry['id'])
        assert response.status_code==200 and response.json()['kind']==entry.get('kind','synthetic')


def test_user_scale_and_manual_edit_do_not_masquerade_as_dataset_measurements():
    c=TestClient(app)
    body={'scene_id':'ctvg-01','scene_mm_per_pixel':.06,'scene_scale_mode':'user_calibrated'}
    result=c.post('/api/layouts',json=body).json()
    assert result['status']=='success' and result['scale_status']=='user_calibrated'
    assert 'not a dataset measurement' in result['scale_note']
    body={'source_scene_id':'ctvg-01','material_mm':{'type':'Polygon','coordinates':[[[0,0],[10,0],[10,10],[0,10],[0,0]]]},'scene_scale_mode':'illustrative'}
    result=c.post('/api/layouts',json=body).json()
    assert result['status']=='success' and result['annotation_source']=='custom_outline'
    svg=c.post('/api/layouts/svg',json=body)
    assert svg.status_code==200 and 'CC BY 4.0' in svg.text and 'ILLUSTRATIVE SCALE' in svg.text


def test_importer_preserves_source_topology_and_rejects_unrepresentable_annotations():
    import importlib.util
    spec=importlib.util.spec_from_file_location('ctvg_import_test',ROOT/'tools/import_ctvg.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    items=[{'segmentation':[[0,0],[10,0],[10,10],[0,10]]},{'segmentation':[[20,0],[30,0],[30,10],[20,10]]}]
    label={'image':{'width':448,'height':448,'n_polygons':2,'polygons':items}}
    geometry=module.annotation_geometry(label)
    assert geometry.geom_type=='MultiPolygon' and len(geometry.geoms)==2
    # CTVG has flat contours, not nested hole rings. Reject instead of flattening.
    label['image']['polygons'][0]['segmentation']=[[[0,0],[10,0],[0,10]]]
    with pytest.raises(ValueError):module.annotation_geometry(label)


def test_imported_selected_assets_regenerate_without_full_dataset(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('ctvg_reimport_test',ROOT/'tools/import_ctvg.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    originals=json.loads((ROOT/'backend/app/ctvg-scenes.json').read_text())
    for record,(scene_id,title,stem) in zip(originals,module.SAMPLES):
        jpeg=(ROOT/'public'/record['image'].lstrip('/')).read_bytes()
        raw=(ROOT/'public'/record['annotation_provenance']['annotation_url'].lstrip('/')).read_bytes()
        regenerated=module.build_sample(scene_id,title,stem,jpeg,raw,tmp_path)
        assert json.loads(json.dumps(regenerated))==record
        assert (tmp_path/f'{scene_id}-mask.svg').read_bytes()==(ROOT/'public'/record['mask'].lstrip('/')).read_bytes()
        assert (tmp_path/f'{scene_id}.jpeg').read_bytes()==jpeg
        assert (tmp_path/f'{scene_id}.json').read_bytes()==raw
