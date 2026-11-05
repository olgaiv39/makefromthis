"""Real CTVG photo -> annotation -> explicit illustrative scale -> fit -> SVG.

Actual in-process FastAPI requests and independent geometry checks. No AI calls.
"""
import io
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fastapi.testclient import TestClient
from PIL import Image
from shapely.geometry import shape
from app.main import app
from app.geometry import mask_to_mm
from app.nesting import verify


def run():
    report={'transport':'real in-process FastAPI TestClient, not a browser/network test',
            'physical_scale_available':False,'inference_calls':0,'results':[]}
    with TestClient(app) as c:
        # Explicit internal regression fixtures, never public craft-photo acceptance.
        real=[c.get(f'/api/demo-scenes/ctvg-{i:02}').json() for i in range(1,5)]
        assert len(real)==4
        for scene in real:
            photo=c.get(scene['image']);assert photo.status_code==200
            with Image.open(io.BytesIO(photo.content)) as image:assert image.size==(448,448)
            assert c.get(scene['thumbnail']).status_code==200
            annotation=c.get(scene['annotation_provenance']['annotation_url']);assert annotation.status_code==200
            assert c.get('/api/demo-scenes/'+scene['id']+'/material').json()['units']=='px'
            assert c.post('/api/layouts',json={'scene_id':scene['id']}).status_code==422
            assert c.post('/api/layouts/svg',json={'scene_id':scene['id']}).status_code==422
            mm=scene['illustrative_mm_per_pixel']
            material=mask_to_mm(ROOT/'public'/scene['mask'].lstrip('/'),mm)
            for project in c.get('/api/project-templates').json():
                body={'scene_id':scene['id'],'template_id':project['id'],'scene_mm_per_pixel':mm,'scene_scale_mode':'illustrative','clearance_mm':.5,'grid_mm':.5}
                r=c.post('/api/layouts',json=body);assert r.status_code==200,r.text
                layout=r.json();assert layout['status']=='success' and layout['verification']['valid']
                assert layout['physically_calibrated'] is False
                expected={f'part-{i+1:02}':shape(g) for i,g in enumerate(project['parts'])}
                assert verify(material,expected,[{**p,'geometry':shape(p['geometry'])} for p in layout['placements']],.5)['valid']
                svg=c.post('/api/layouts/svg',json=body);assert svg.status_code==200
                assert 'ILLUSTRATIVE SCALE ONLY' in svg.text and 'CC BY 4.0' in svg.text
                assert ET.fromstring(svg.text).attrib['width'].endswith('mm')
                report['results'].append({'scene_id':scene['id'],'source_image':scene['annotation_provenance']['source_image'],
                    'template_id':project['id'],'status':layout['status'],'layout_http_status':r.status_code,'svg_http_status':svg.status_code,
                    'scale_status':'illustrative','assumed_mm_per_pixel':mm,'measured_dimensions':False,
                    'illustrative_area_mm2':layout['material_area_mm2'],'utilization_percent':layout['utilization_percent']})
                print(scene['id'],project['id'],'verified success; illustrative scale only')
    (ROOT/'docs/REAL_DATASET_FITS.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':run()
