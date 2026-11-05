"""Reproducible real-API presentation fit report, without any inference calls."""
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.geometry import mask_to_mm
from app.nesting import verify
from shapely.geometry import shape


def run():
    report={'transport':'real FastAPI app via in-process TestClient; not a live network/browser test',
            'clearance_mm':.5,'grid_mm':.5,'inference_calls':0,'results':[]}
    with TestClient(app) as client:
        projects=client.get('/api/project-templates').json()
        for scene in [client.get(f'/api/demo-scenes/scene-{i:02}').json() for i in range(1,7)]:
            material=mask_to_mm(ROOT/'public'/scene['mask'].lstrip('/'),scene['mm_per_pixel'])
            for project in projects:
                body={'scene_id':scene['id'],'template_id':project['id'],'clearance_mm':.5,'grid_mm':.5}
                response=client.post('/api/layouts',json=body)
                assert response.status_code==200,response.text
                result=response.json()
                entry={'scene_id':scene['id'],'title':scene['title'],'template_id':project['id'],
                       'status':result['status'],'area_mm2':result['material_area_mm2'],
                       'utilization_percent':result['utilization_percent']}
                if result['status']=='success':
                    expected={f'part-{i+1:02}':shape(p) for i,p in enumerate(project['parts'])}
                    placements=[{**p,'geometry':shape(p['geometry'])} for p in result['placements']]
                    assert verify(material,expected,placements,.5)['valid']
                    svg=client.post('/api/layouts/svg',json=body)
                    assert svg.status_code==200 and ET.fromstring(svg.text).attrib['width'].endswith('mm')
                    if scene['id']=='scene-01':
                        # Keep the earlier example API exports consistent with the refreshed default scene.
                        target=ROOT/'examples/stage02'/project['id']
                        target.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
                        target.with_suffix('.svg').write_text(svg.text)
                else:
                    assert scene['id']=='scene-06' and material.buffer(-.5).is_empty
                    assert not result['placements'] and not result['verification']['valid']
                    assert client.post('/api/layouts/svg',json=body).status_code==422
                    entry['infeasibility_certificate']='Material eroded by 0.5 mm is empty.'
                report['results'].append(entry)
                print(scene['id'],project['id'],entry['status'])
    (ROOT/'docs/DEMO_SCENE_FITS.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    run()
