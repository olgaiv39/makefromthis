"""Stage 03 UI request contracts exercised against real geometry, without mocks."""
from xml.etree import ElementTree as ET
import pytest
pytest.importorskip('shapely', reason='Web layout flow requires the Stage 02 geometry dependency')
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)


def assert_svg(body, expected_width=None):
    result = client.post('/api/layouts', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'success'
    assert result.json()['verification']['valid']
    download = client.post('/api/layouts/svg', json=body)
    assert download.status_code == 200, download.text
    svg = ET.fromstring(download.text)
    assert svg.attrib['width'].endswith('mm') and svg.attrib['height'].endswith('mm')
    assert len(svg.findall('{http://www.w3.org/2000/svg}path')) == len(result.json()['placements']) + 1
    if expected_width is not None:
        assert float(svg.attrib['width'][:-2]) == pytest.approx(expected_width)
    return result.json()


def test_demo_scene_project_selection_and_download():
    scenes = [client.get(f'/api/demo-scenes/scene-{i:02}').json() for i in range(1,4)]
    projects = client.get('/api/project-templates').json()
    assert len(projects) == 3
    for scene in scenes[:3]:
        assert 'synthetic' in scene['source']
        for project in projects:
            assert_svg({'scene_id': scene['id'], 'template_id': project['id'], 'clearance_mm': .5, 'grid_mm': .5})


def test_manually_traced_upload_coordinates_calibration_and_download():
    # UI decodes a 400x280 uploaded raster, traces this rectangle in pixels,
    # and applies a user-supplied width of 80 mm / 320 pixels = .25 mm/px.
    points = [(40,40),(360,40),(360,240),(40,240),(40,40)]
    material = {'type':'Polygon', 'coordinates':[[[x*.25,y*.25] for x,y in points]]}
    for project in client.get('/api/project-templates').json():
        result = assert_svg({'material_mm': material, 'template_id':project['id'], 'clearance_mm':.5, 'grid_mm':1.2},80)
        assert result['material_area_mm2'] == pytest.approx(4000)


def test_invalid_trace_and_excessive_search_cannot_export():
    crossing = {'type':'Polygon','coordinates':[[[0,0],[4,3],[0,3],[3,0],[0,0]]]}
    assert client.post('/api/layouts',json={'material_mm':crossing}).status_code == 422
    assert client.post('/api/layouts/svg',json={'material_mm':crossing}).status_code == 422
    assert client.post('/api/layouts',json={'grid_mm':.00001}).status_code == 422


@pytest.mark.parametrize('material', [
    {}, {'type':'Polygon','coordinates':None},
    {'type':'MultiPolygon','coordinates':[{}]},
    {'type':'GeometryCollection','geometries':[]},
])
def test_malformed_geometry_returns_validation_error(material):
    assert client.post('/api/layouts',json={'material_mm':material}).status_code == 422
