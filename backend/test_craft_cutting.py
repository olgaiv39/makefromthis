"""Practical custom cutting through existing public APIs; no model or photo claims."""
from xml.etree import ElementTree as ET
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping, shape
from app.main import app
from app.nesting import verify


def request(width,height,quantity,material=(120,100),gap=.5):
    return {'template_id':'custom-rectangles','scene_scale_mode':'user_calibrated',
        'material_mm':mapping(box(0,0,*material)),
        'parts_mm':[mapping(box(0,0,width,height)) for _ in range(quantity)],
        'clearance_mm':gap,'grid_mm':2}


def test_size_and_quantity_produce_verified_physical_cutting_paths():
    body=request(30,20,6)
    with TestClient(app) as client:
        response=client.post('/api/layouts',json=body)
        assert response.status_code==200,response.text
        layout=response.json();assert layout['status']=='success' and len(layout['placements'])==6
        expected={f'part-{i+1:02}':shape(g) for i,g in enumerate(body['parts_mm'])}
        assert verify(shape(body['material_mm']),expected,[{**p,'geometry':shape(p['geometry'])} for p in layout['placements']],.5)['valid']
        for item in layout['placements']:
            assert shape(item['geometry']).area==600
        svg=client.post('/api/layouts/svg',json=body)
        assert svg.status_code==200
        root=ET.fromstring(svg.text)
        assert root.attrib['width']=='120mm' and root.attrib['height']=='100mm'
        assert len(root.findall('{http://www.w3.org/2000/svg}path[@data-part]'))==6


def test_custom_parts_retain_quarter_turn_support():
    body=request(30,20,1,material=(20,30),gap=0)
    with TestClient(app) as client:
        result=client.post('/api/layouts',json=body).json()
        assert result['status']=='success' and result['placements'][0]['rotation_deg']==90


def test_insufficient_space_reports_missing_pieces_and_refuses_export():
    body=request(30,20,6,material=(40,30))
    with TestClient(app) as client:
        result=client.post('/api/layouts',json=body).json()
        assert result['status']=='incomplete'
        assert len(result['placements'])+len(result['verification']['missing_parts'])==6
        assert len(result['placements'])<6 and not result['verification']['valid']
        assert client.post('/api/layouts/svg',json=body).status_code==422


@pytest.mark.parametrize('parts',[[],[mapping(box(0,0,1,1))]*51])
def test_custom_quantity_stays_within_existing_server_limits(parts):
    body=request(1,1,1);body['parts_mm']=parts
    with TestClient(app) as client:
        assert client.post('/api/layouts',json=body).status_code==422
        assert client.post('/api/layouts/svg',json=body).status_code==422
