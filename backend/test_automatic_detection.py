"""Offline pixel tests and explicitly mocked HTTP transports. No live inference."""
import asyncio
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx
import numpy as np
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from shapely.geometry import shape, box, mapping
from app.main import app
from app.material_detection import decode_photo,detect_outline,vision_image,DetectionError
from app.providers.core import Config,Runtime,ProviderError
from app.providers.baseten import CHAT_ENDPOINT,HACKATHON_MODEL
from app.ai_api import MaterialGuidance

REAL_CUTTING_MAT=Path(__file__).resolve().parents[1]/'examples/craft_photos/incoming/Cutting_mat.jpg'
REAL_SEWING_TOOLS=REAL_CUTTING_MAT.with_name('Cutting_tools_sewing.jpg')

def test_real_tools_and_multiple_fabrics_are_rejected_instead_of_outer_mat():
    import hashlib
    raw=REAL_SEWING_TOOLS.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='13cad077d18679c6cd138ba315bd3fd6722e310c40cf46d0590998674346159d'
    with pytest.raises(DetectionError,match='material_scene_ambiguous'):
        detect_outline(decode_photo(raw,'image/jpeg'))
    assert REAL_SEWING_TOOLS.read_bytes()==raw

def test_real_occluded_photo_returns_no_usable_material_geometry(monkeypatch):
    def forbidden(request):raise AssertionError('No inference in this negative regression')
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(forbidden),False))
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material?use_ai=false',content=REAL_SEWING_TOOLS.read_bytes(),headers={'content-type':'image/jpeg'})
        assert response.status_code==422 and response.json()=={'detail':'material_scene_ambiguous'}

@pytest.mark.parametrize('patterned',[False,True])
def test_large_rectangular_material_is_allowed_when_no_compound_scene_evidence(patterned):
    # Procedural unit inputs, never photographic demo substitutes. Similar frame
    # occupancy/rectangularity to the false mask must not itself cause rejection.
    image=Image.new('RGB',(320,240),(12,18,22));draw=ImageDraw.Draw(image)
    draw.rectangle((12,12,308,228),fill=(205,195,165))
    if patterned:
        for y in range(30,210,24):
            for x in range(30,295,24):
                draw.rectangle((x,y,x+10,y+10),fill=(75,110,165))
    result=detect_outline(image);g=shape(result['geometry_px'])
    assert g.is_valid and g.area/(320*240)>.8 and g.area/g.envelope.area>.98
    assert result['requires_confirmation']

def test_large_isolated_contrasting_surface_inside_material_is_ambiguous():
    image=Image.new('RGB',(320,240),(12,18,22));draw=ImageDraw.Draw(image)
    draw.rectangle((25,25,295,215),fill=(205,195,165))
    draw.rectangle((105,80,205,160),fill=(165,35,90))
    with pytest.raises(DetectionError,match='material_scene_ambiguous'):detect_outline(image)

def assert_real_fabric_outline(result):
    """Sparse visual reference pixels in the real 800x600 JPEG, no supplied mask.

    Cloth occupies the lower centre/right, with an upper edge rising to the right.
    The green mat surrounds it; the tabletop is visible above/below the mat.
    """
    from shapely.geometry import Point,LineString
    g=shape(result['geometry_px'])
    assert result['width_px']==800 and result['height_px']==600
    assert g.geom_type=='Polygon' and g.is_valid and not g.interiors
    assert g.exterior.coords[0]==g.exterior.coords[-1] and 3<=len(g.exterior.coords)-1<=100
    assert box(1,1,799,599).contains(g)
    assert .26<g.area/(800*600)<.32
    assert g.area/g.envelope.area<.65 # A bounding rectangle would include substantial mat.
    # Fabric interior: left strip, central body, and tall right end.
    inside=[(80,385),(200,400),(400,390),(600,340),(720,230),(745,420)]
    # Mat above/beside/below fabric, including grid/shadow patches and loose tails.
    mat=[(100,200),(350,250),(500,200),(620,180),(700,100),(795,300),
         (300,500),(600,500),(200,475),(750,480),(70,490)]
    tabletop=[(50,15),(400,15),(200,560),(700,570)]
    assert all(g.contains(Point(p)) for p in inside)
    assert all(not g.covers(Point(p)) for p in mat+tabletop)
    # Bracket the visible sloping/curved upper fabric edge at four image columns.
    for x,low,high in [(100,330,350),(400,300,320),(600,220,240),(700,145,165)]:
        upper_y=g.intersection(LineString([(x,0),(x,600)])).bounds[1]
        assert low<upper_y<high,(x,upper_y)
    assert result['requires_confirmation'] is True

def test_real_cutting_mat_fabric_contour_includes_cloth_and_excludes_both_backgrounds():
    import hashlib
    original=REAL_CUTTING_MAT.read_bytes()
    assert hashlib.sha256(original).hexdigest()=='a4bbc12bfcbc50214e2d1438ca0b3dc1abef98f5bd54bc27863eab79ac034b0d'
    image=decode_photo(original,'image/jpeg')
    result=detect_outline(image)
    assert_real_fabric_outline(result)
    assert result['quality']['method']=='spatial_background_and_grabcut'
    assert detect_outline(image)==result # Deterministic hypotheses and GrabCut seeds.
    assert REAL_CUTTING_MAT.read_bytes()==original

def test_real_cutting_mat_offline_upload_endpoint_returns_reviewable_fabric_outline(monkeypatch):
    def forbidden(request):raise AssertionError('No AI calls permitted for this real-photo regression')
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(forbidden),False))
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material?use_ai=false',content=REAL_CUTTING_MAT.read_bytes(),headers={'content-type':'image/jpeg'})
        assert response.status_code==200,response.text
        assert_real_fabric_outline(response.json())
        assert response.json()['status']=='review_required'
        assert response.json()['provenance']['ai_image_understanding'] is False
        assert response.json()['provenance']['outline_source']=='opencv_pixel_segmentation'


def photo(background=(230,230,230),foreground=(55,85,150),hole=False,two=False):
    # Procedural unit-test input ONLY, never a demo asset or photographic claim.
    image=Image.new('RGB',(320,240),background)
    draw=ImageDraw.Draw(image)
    draw.polygon([(65,42),(250,50),(265,175),(180,198),(58,180)],fill=foreground)
    if hole:draw.rectangle((135,95,170,130),fill=background)
    if two:
        image=Image.new('RGB',(320,240),background);draw=ImageDraw.Draw(image)
        draw.rectangle((30,40,120,200),fill=foreground);draw.rectangle((190,40,290,200),fill=foreground)
    return image

def encoded(image,fmt='PNG',**kwargs):
    out=io.BytesIO();image.save(out,fmt,**kwargs);return out.getvalue()

def runtime(transport=None,enabled=True):
    return Runtime(enabled=enabled,recommendation=Config(provider='baseten',endpoint=CHAT_ENDPOINT,model=HACKATHON_MODEL,
        token='TEST_ONLY_NEVER_REAL_KEY',auth='bearer',protocol='openai'),transport=transport)

def completion(content,finish='stop'):
    return {'model':HACKATHON_MODEL,'choices':[{'finish_reason':finish,'message':{'content':content}}],
        'usage':{'completion_tokens':80,'completion_tokens_details':{'reasoning_tokens':12}}}

GUIDE={'material_type':'fabric','flat_for_cutting':True,'region':[.15,.1,.9,.9],'issues':[]}

@pytest.mark.parametrize('bg,fg',[( (238,238,238),(60,90,145)),((20,25,30),(190,145,100)),((160,205,170),(160,45,95))])
def test_pixel_segmentation_varied_backgrounds_is_valid_and_deterministic(bg,fg):
    image=photo(bg,fg);a=detect_outline(image);b=detect_outline(image)
    assert a==b
    g=shape(a['geometry_px'])
    assert g.is_valid and g.geom_type=='Polygon' and len(g.interiors)==0
    assert box(0,0,320,240).contains(g) and 20000<g.area<40000
    assert a['requires_confirmation'] and len(g.exterior.coords)<=101
    # The notch/asymmetry comes from pixels; it is not the bounding rectangle.
    assert g.area<g.envelope.area*.94

def test_gradient_background_and_textured_material():
    array=np.asarray(photo()).copy()
    ramp=np.linspace(-15,15,320).astype(np.int16)[None,:,None]
    array=np.clip(array.astype(np.int16)+ramp,0,255).astype(np.uint8)
    array[75:170:5,80:230]=[65,95,155]
    assert shape(detect_outline(Image.fromarray(array))['geometry_px']).is_valid

@pytest.mark.parametrize('image,code',[(Image.new('RGB',(320,240),'gray'),'foreground_not_clear'),
    (photo(hole=True),'internal_holes_unsupported'),(photo(two=True),'multiple_material_pieces')])
def test_ambiguous_holes_or_disconnected_material_refused(image,code):
    with pytest.raises(DetectionError,match=code):detect_outline(image)

@pytest.mark.parametrize('image,code',[(photo(hole=True),'internal_holes_unsupported'),
    (photo(two=True),'multiple_material_pieces'),(Image.new('RGB',(320,240),'gray'),'foreground_not_clear')])
def test_spatial_hypotheses_preserve_negative_image_refusals(image,code):
    from app.material_detection import _interior_background_outline
    import cv2
    cv2.setNumThreads(1);cv2.setRNGSeed(0)
    with pytest.raises(DetectionError,match=code):
        _interior_background_outline(image,np.asarray(image),None,DetectionError('foreground_not_clear'))

def test_spatial_hypotheses_refuse_material_touching_photo_frame():
    from app.material_detection import _interior_background_outline
    import cv2
    image=photo();ImageDraw.Draw(image).rectangle((0,40,80,190),fill=(55,85,150))
    cv2.setNumThreads(1);cv2.setRNGSeed(0)
    with pytest.raises(DetectionError):
        _interior_background_outline(image,np.asarray(image),None,DetectionError('foreground_not_clear'))

def test_image_border_contact_refused():
    image=photo();ImageDraw.Draw(image).rectangle((0,40,80,190),fill=(55,85,150))
    with pytest.raises(DetectionError):detect_outline(image)

def test_exif_orientation_and_bounded_metadata_free_vision_image():
    exif=Image.Exif();exif[274]=6;exif[270]='TEST_ONLY_PRIVATE_METADATA'
    data=encoded(photo(),'JPEG',exif=exif)
    decoded=decode_photo(data,'image/jpeg')
    assert decoded.size==(240,320)
    resized=vision_image(decoded)
    with Image.open(io.BytesIO(resized)) as image:
        assert not image.getexif() and max(image.size)<=1024
    assert len(resized)<=1024*1024 and b'TEST_ONLY_PRIVATE_METADATA' not in resized
    assert detect_outline(decoded)['width_px']==240

@pytest.mark.parametrize('data,mime',[(b'not an image','image/png'),(encoded(photo()),'image/jpeg'),(encoded(photo()),'image/svg+xml')])
def test_image_upload_rejects_invalid_or_mismatched_media(data,mime):
    with pytest.raises(DetectionError):decode_photo(data,mime)

@pytest.mark.parametrize('change',[{'region':[-.1,.1,.9,.9]},{'region':[.8,.1,.2,.9]},
    {'region':[0.,0.,float('nan'),1.]},{'flat_for_cutting':'yes'},{'material_type':'invented'},
    {'issues':['made_up']},{'polygon':[[0,0],[1,1]]}])
def test_model_guidance_is_strictly_validated(change):
    with pytest.raises(ValueError):MaterialGuidance.model_validate({**GUIDE,**change})

def test_folded_or_obscured_photo_is_refused_even_with_good_pixels():
    with pytest.raises(DetectionError,match='photo_not_suitable'):
        detect_outline(photo(),{**GUIDE,'issues':['folds']})

def test_model_localization_never_crops_pixels_into_a_fake_rectangle():
    with pytest.raises(DetectionError,match='guidance_region_incomplete'):
        detect_outline(photo(),{**GUIDE,'region':[.4,.4,.65,.65]})

def test_busy_segmentation_refuses_queueing():
    from app.material_detection import _CV_LOCK
    with _CV_LOCK:
        with pytest.raises(DetectionError,match='detection_busy'):detect_outline(photo())

def test_vision_timeout_cancels_single_request_without_retry():
    calls=[]
    async def slow(request):
        calls.append(1);await asyncio.sleep(.1)
        return httpx.Response(200,json=completion(json.dumps(GUIDE)))
    r=runtime(httpx.MockTransport(slow));r.timeout=.01
    with pytest.raises(ProviderError,match='provider_timeout'):
        asyncio.run(r.call('material_vision',vision_image(photo()),MaterialGuidance.model_json_schema()))
    assert len(calls)==1

def test_missing_credentials_fail_before_any_vision_request():
    def forbidden(request):raise AssertionError('Must not send request')
    r=runtime(httpx.MockTransport(forbidden));r.recommendation.token=''
    with pytest.raises(ProviderError,match='credentials_missing'):
        asyncio.run(r.call('material_vision',vision_image(photo()),MaterialGuidance.model_json_schema()))

def test_detection_upload_size_limit():
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material',content=b'x'*(8*1024*1024+1),headers={'content-type':'image/jpeg'})
        assert response.status_code==413

def test_baseten_multimodal_serialization_exact_profile_and_no_secret_exposure(monkeypatch,capsys):
    calls=[]
    def handler(request):
        calls.append(request)
        payload=json.loads(request.content)
        assert str(request.url)==CHAT_ENDPOINT and request.headers['authorization']=='Bearer TEST_ONLY_NEVER_REAL_KEY'
        assert payload['model']==HACKATHON_MODEL and payload['reasoning_effort']=='low'
        assert payload['temperature']==1.0 and payload['max_tokens']==1024
        content=payload['messages'][1]['content']
        assert content[1]['type']=='image_url' and content[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        assert payload['response_format']['json_schema']['strict'] is True
        return httpx.Response(200,json=completion(json.dumps(GUIDE)))
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(handler)))
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material?use_ai=true',content=encoded(photo()),headers={'content-type':'image/png'})
        assert response.status_code==200,response.text
        data=response.json();assert data['provenance']['ai_image_understanding'] is True
        assert data['provenance']['outline_source']=='opencv_pixel_segmentation'
        assert 'TEST_ONLY_NEVER_REAL_KEY' not in response.text
        assert data['geometry_px']!=mapping(box(48,24,288,216))
    captured=capsys.readouterr();assert 'TEST_ONLY_NEVER_REAL_KEY' not in captured.out+captured.err
    assert len(calls)==1

@pytest.mark.parametrize('payload,finish,code',[(json.dumps(GUIDE),'length','incomplete_provider_output'),
    ('','stop','malformed_provider_output'),('not json','stop','malformed_provider_output'),
    (json.dumps({**GUIDE,'region':[0.,0.,2.,1.]}),'stop','invalid_material_guidance')])
def test_invalid_ai_response_is_not_substituted_with_fake_success(monkeypatch,payload,finish,code):
    calls=[]
    def handler(request):calls.append(1);return httpx.Response(200,json=completion(payload,finish))
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(handler)))
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material?use_ai=true',content=encoded(photo()),headers={'content-type':'image/png'})
        assert response.status_code==502 and response.json()['detail']==code
    assert len(calls)==1

@pytest.mark.parametrize('status,code',[(401,'provider_authentication_failed'),(503,'provider_unavailable')])
def test_vision_http_failures_are_sanitized_without_retry(monkeypatch,status,code):
    calls=[]
    def handler(request):calls.append(1);return httpx.Response(status,json={'untrusted':'SECRET_CONTENT'})
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(handler)))
    with TestClient(app) as client:
        response=client.post('/api/ai/detect-material?use_ai=true',content=encoded(photo()),headers={'content-type':'image/png'})
        assert response.json()['detail']==code and 'SECRET_CONTENT' not in response.text
    assert len(calls)==1

def test_disabled_ai_uses_real_offline_processing_only_when_requested(monkeypatch):
    def forbidden(request):raise AssertionError('No inference permitted')
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(forbidden),False))
    with TestClient(app) as client:
        body=encoded(photo());headers={'content-type':'image/png'}
        assert client.post('/api/ai/detect-material?use_ai=true',content=body,headers=headers).status_code==503
        response=client.post('/api/ai/detect-material',content=body,headers=headers)
        assert response.status_code==200 and response.json()['provenance']['ai_image_understanding'] is False
        assert response.json()['provenance']['scale_inferred'] is False

@pytest.mark.parametrize('kind',['photograph','unclear','invalid'])
def test_offline_photo_upload_returns_outline_or_actionable_detection_error(monkeypatch,kind):
    def forbidden(request):raise AssertionError('Offline upload must not contact any AI provider')
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(forbidden),False))
    if kind=='photograph':
        data=(Path(__file__).resolve().parents[1]/'public/ctvg/ctvg-01.jpeg').read_bytes();mime='image/jpeg'
    else:
        data=encoded(Image.new('RGB',(320,240),'gray')) if kind=='unclear' else b'not an image'
        mime='image/png'
    with TestClient(app,base_url='http://127.0.0.1:8000') as client:
        response=client.post('/api/ai/detect-material?use_ai=false',content=data,headers={'content-type':mime})
        assert 'application/json' in response.headers['content-type']
        assert "connect-src 'self' blob:;" in response.headers['content-security-policy']
        if kind=='photograph':
            assert response.status_code==200,response.text
            result=response.json();assert result['status']=='review_required' and result['requires_confirmation']
            assert result['provenance']['ai_image_understanding'] is False
            assert shape(result['geometry_px']).is_valid
        else:
            assert response.status_code==422
            assert response.json()['detail']==('foreground_not_clear' if kind=='unclear' else 'invalid_image')

def test_vision_cannot_switch_to_other_providers_or_generic_model():
    for provider,model in [('modal',HACKATHON_MODEL),('baseten','meta-models/muse-spark-open')]:
        r=runtime();r.recommendation.provider=provider;r.recommendation.model=model
        assert not r.availability('material_vision')['available']

def test_existing_real_photo_pixel_outline_to_calibrated_rectangles_and_svg(monkeypatch):
    monkeypatch.setattr(app.state,'ai_runtime',runtime(enabled=False))
    source=Path(__file__).resolve().parents[1]/'public/ctvg/ctvg-01.jpeg'
    with TestClient(app,base_url='http://127.0.0.1:8000') as client:
        assert client.get('/api/demo-scenes').json()==[] # Never synthetic fallback.
        detected=client.post('/api/ai/detect-material',content=source.read_bytes(),headers={'content-type':'image/jpeg'})
        assert detected.status_code==200,detected.text
        material=shape(detected.json()['geometry_px']);x,y,a,b=material.bounds
        # Explicit TEST user measurement, not a claim about the source's actual size.
        from shapely.affinity import scale
        material=scale(material,xfact=120/(a-x),yfact=120/(a-x),origin=(0,0))
        body={'template_id':'custom-rectangles','material_mm':mapping(material),'scene_scale_mode':'user_calibrated',
              'parts_mm':[mapping(box(0,0,20,15))]*4,'clearance_mm':1,'grid_mm':4}
        fitted=client.post('/api/layouts',json=body)
        assert fitted.status_code==200,fitted.text
        assert fitted.json()['status']=='success' and fitted.json()['verification']['valid']
        svg=client.post('/api/layouts/svg',json=body)
        assert svg.status_code==200 and 'image/svg+xml' in svg.headers['content-type']
        assert ET.fromstring(svg.text).attrib['width'].endswith('mm')

def test_product_ideas_only_rank_real_sized_verified_options(monkeypatch):
    seen=[]
    def handler(request):
        context=json.loads(json.loads(request.content)['messages'][1]['content']);seen.extend(context['verified_templates'])
        return httpx.Response(200,json=completion(json.dumps({'ranked_projects':[{'project_id':context['verified_templates'][0]['project_id'],'explanation':'Checked paper blanks at a fitting size.'}]})))
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(handler)))
    body={'material_type':'paper','material_mm':mapping(box(0,0,120,100)),'width_mm':120,'height_mm':100,
          'piece_width_mm':30,'piece_height_mm':20,'quantity':4,'clearance_mm':1,'grid_mm':4}
    with TestClient(app) as client:
        response=client.post('/api/ai/cutting-ideas',json=body)
        assert response.status_code==200,response.text
        assert response.json()['status']=='live_ai' and seen[0]['width_mm']==30
        assert len(seen)<=6 and all(o['verified'] and min(o['width_mm'],o['height_mm'])>=5 for o in seen)
        body.update(piece_width_mm=200,piece_height_mm=200)
        before=len(seen);response=client.post('/api/ai/cutting-ideas',json=body)
        assert response.json()['status']=='live_ai' and len(seen)>before
        assert all(o['project_id']!='rectangles' for o in seen[before:])

@pytest.mark.parametrize('key',['square-tabs','unknown','rectangles'])
def test_unknown_or_infeasible_product_ideas_refused(monkeypatch,key):
    def handler(request):return httpx.Response(200,json=completion(json.dumps({'ranked_projects':[{'project_id':key,'explanation':'Test-only'}]})))
    monkeypatch.setattr(app.state,'ai_runtime',runtime(httpx.MockTransport(handler)))
    # Rectangles do not fit, but the half-size option does. Unknown/full-size IDs must fail.
    body={'material_mm':mapping(box(0,0,50,40)),'width_mm':50,'height_mm':40,
          'piece_width_mm':60,'piece_height_mm':40,'quantity':1,'clearance_mm':1,'grid_mm':3}
    with TestClient(app) as client:
        response=client.post('/api/ai/cutting-ideas',json=body)
        assert response.status_code==502 and response.json()['detail']=='invalid_recommendation_output'

def test_local_and_container_bind_urls(monkeypatch):
    import importlib.util
    path=Path(__file__).resolve().parents[1]/'tools/start_release.py'
    spec=importlib.util.spec_from_file_location('mft_start_release',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.configuration({})==('127.0.0.1',8000,'http://127.0.0.1:8000')
    assert module.configuration({'BIND_HOST':'0.0.0.0','PORT':'9000'})==('0.0.0.0',9000,'http://127.0.0.1:9000')
    with pytest.raises(ValueError):module.configuration({'PORT':'0'})
