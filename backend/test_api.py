from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
def test_health(): assert c.get('/health').json()['status']=='ok'
def test_scenes():
 r=c.get('/api/demo-scenes'); assert r.status_code==200 and r.json()==[]
 # Every proposed craft-photo original failed download; do not replace with fixtures.

def test_detail_and_missing():
 from app.main import DATA, Scene
 data=DATA
 for entry in data:
  r=c.get('/api/demo-scenes/'+entry['id'])
  assert r.status_code==200 and r.json()==Scene.model_validate(entry).model_dump()
 assert c.get('/api/demo-scenes/unknown').status_code==404

def test_gallery_rejects_synthetic_legacy_and_hidden_entries(monkeypatch):
 from app import main
 # Catalog contract fixture only: no photo bytes, annotations or acceptance results.
 photo={'id':'TEST_ONLY_UNANNOTATED','kind':'photograph','annotation_source':'manual_required',
  'source':'TEST_ONLY','image':'/TEST_ONLY_NOT_AN_ASSET.jpg','width_px':100,'height_px':100,'mm_per_pixel':None}
 dataset=next(s for s in main.DATA if s.get('kind')=='photograph')
 monkeypatch.setattr(main,'PUBLIC_DATA',[photo,{**photo,'id':'hidden','gallery_visible':False},
  {**photo,'id':'synthetic','kind':'synthetic','gallery_visible':True},dataset,
  {**photo,'id':'hidden-outline','polygon_px':[[0,0],[1,0],[0,1]]},
  {k:v for k,v in photo.items() if k!='kind'}])
 response=c.get('/api/demo-scenes')
 assert response.status_code==200 and [s['id'] for s in response.json()]==[photo['id']]
 assert response.json()[0]['polygon_px']==[] and response.json()[0]['mask'] is None

def test_assets_and_determinism():
 import hashlib, subprocess, sys
 from pathlib import Path
 from xml.etree import ElementTree as ET
 root=Path(__file__).resolve().parents[1]
 data=[c.get(f'/api/demo-scenes/scene-{i:02}').json() for i in range(1,13)]
 assert len(data)==12 and len({s['id'] for s in data})==12
 files=[root/'backend/app/scenes.json', *sorted((root/'public/scenes').glob('*.svg'))]
 assert len(files)==25
 files.append(root/'docs/presentation-scenes.svg')
 before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
 subprocess.run([sys.executable,str(root/'tools/generate_scenes.py')],check=True)
 assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
 for s in data:
  assert 'synthetic' in s['source'] and s['mm_per_pixel']>0
  points=s['polygon_px']
  assert len(points)>=3
  assert all(0<=x<s['width_px'] and 0<=y<s['height_px'] for x,y in points)
  assert abs(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points))))>0
  full=s['geometry_px']
  polygons=[full['coordinates']] if full['type']=='Polygon' else full['coordinates']
  assert polygons[0][0][:-1]==points
  assert all(r[0]==r[-1] for polygon in polygons for r in polygon)
  assert all(0<=x<s['width_px'] and 0<=y<s['height_px'] for polygon in polygons for r in polygon for x,y in r)
  image=ET.parse(root/'public'/s['image'].lstrip('/')).getroot()
  mask=ET.parse(root/'public'/s['mask'].lstrip('/')).getroot()
  for svg in (image,mask):
   assert int(svg.attrib['width'])==s['width_px'] and int(svg.attrib['height'])==s['height_px']
  actual=mask.findall('{http://www.w3.org/2000/svg}polygon')
  expected=[(ring,'white' if index==0 else 'black') for polygon in polygons for index,ring in enumerate(polygon)]
  assert len(actual)==len(expected)
  for element,(ring,color) in zip(actual,expected):
   assert [[int(v) for v in p.split(',')] for p in element.attrib['points'].split()]==ring[:-1]
   assert element.attrib['fill']==color
  assert {e.attrib['fill'] for e in mask if 'fill' in e.attrib}=={'black','white'}
  image_path=image.find('{http://www.w3.org/2000/svg}path[@data-material="true"]')
  assert image_path is not None and image_path.attrib['fill-rule']=='evenodd'
  expected_path=' '.join('M'+' L'.join(f'{x},{y}' for x,y in ring[:-1])+' Z' for polygon in polygons for ring in polygon)
  assert image_path.attrib['d']==expected_path
