"""Stage 04 public contracts. Provider outputs are untrusted and never bypass nesting."""
import asyncio
import io
import json
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, StrictBool, field_validator
from typing import Literal
from .providers.core import Runtime, ProviderError

MAX_BODY=8*1024*1024
router=APIRouter(prefix='/api/ai')

class BodyLimit:
    """Bound bodies before FastAPI JSON decoding (including chunked requests)."""
    def __init__(self, app): self.app=app
    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or not scope['path'].startswith('/api/ai/'):
            return await self.app(scope,receive,send)
        chunks=[]; size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            size+=len(message.get('body',b''))
            if size>MAX_BODY:
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json')]})
                await send({'type':'http.response.body','body':b'{"detail":"image_or_request_too_large"}'})
                return
            chunks.append(message.get('body',b''))
            if not message.get('more_body'): break
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)

def runtime(request): return request.app.state.ai_runtime

async def inference(request, kind, *args):
    operation=asyncio.create_task(runtime(request).call(kind,*args))
    async def disconnected():
        # The route has consumed its body. Await the ASGI disconnect directly;
        # polling is_disconnected() mixes AnyIO cancel scopes with asyncio tasks.
        while True:
            message = await request.receive()
            if message['type'] == 'http.disconnect': return
    watcher=asyncio.create_task(disconnected())
    try:
        done,_=await asyncio.wait([operation,watcher],return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            raise HTTPException(499,'client_disconnected')
        return await operation
    except ProviderError as exc: raise HTTPException(exc.status,exc.code) from None
    finally:
        for task in (operation,watcher):
            if not task.done(): task.cancel()
        await asyncio.gather(operation,watcher,return_exceptions=True)

@router.get('/availability')
def availability(request:Request):
    r=runtime(request)
    return {'ai_enabled':r.enabled,'segmentation':r.availability('segmentation'),'recommendation':r.availability('recommendation'),
            'material_vision':r.availability('material_vision')}

class MaterialGuidance(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    material_type:Literal['fabric','paper','cardboard','leather','felt','unknown']
    flat_for_cutting:StrictBool
    region:list[float]=Field(min_length=4,max_length=4)
    issues:list[Literal['overlap','folds','occlusion','missing_edges','multiple_pieces','uncertain']]=Field(max_length=6)

    @field_validator('region')
    @classmethod
    def valid_region(cls,region):
        import math
        if not all(math.isfinite(v) for v in region) or not (0<=region[0]<region[2]<=1 and 0<=region[1]<region[3]<=1):
            raise ValueError('invalid_localization')
        if (region[2]-region[0])*(region[3]-region[1])<.02:raise ValueError('region_too_small')
        return region

@router.post('/detect-material')
async def detect_material(request:Request,use_ai:bool=False):
    """One explicit request, at most one inference; offline mode uses pixels only."""
    from .material_detection import decode_photo, vision_image, detect_outline, DetectionError
    try:
        photo=await asyncio.to_thread(decode_photo,await request.body(),request.headers.get('content-type','').split(';')[0])
    except DetectionError as exc:raise HTTPException(422,str(exc)) from None
    guidance=None;r=runtime(request)
    if use_ai:
        response=await inference(request,'material_vision',vision_image(photo),MaterialGuidance.model_json_schema())
        try:guidance=MaterialGuidance.model_validate(response).model_dump()
        except ValidationError:raise HTTPException(502,'invalid_material_guidance') from None
    try:
        result=await asyncio.to_thread(detect_outline,photo,guidance)
    except ImportError:raise HTTPException(503,'image_processing_unavailable') from None
    except DetectionError as exc:raise HTTPException(429 if str(exc)=='detection_busy' else 422,str(exc)) from None
    return {**result,'status':'review_required','material_type':guidance['material_type'] if guidance else 'unknown',
        'provenance':{'outline_source':'opencv_pixel_segmentation','ai_image_understanding':bool(guidance),
                      'provider':'baseten' if guidance else None,'model_id':r.recommendation.model if guidance else None,
                      'scale_inferred':False}}

class Prompts(BaseModel):
    model_config=ConfigDict(extra='forbid')
    points: list[tuple[float,float,int]]=Field(default_factory=list,max_length=32)
    boxes: list[tuple[float,float,float,float]]=Field(default_factory=list,max_length=8)

@router.post('/segment')
async def segment(request:Request, prompts:str='{}'):
    r=runtime(request); state=r.availability('segmentation')
    if not state['available']: raise HTTPException(503,state['reason'])
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError: raise HTTPException(503,'image_decoder_unavailable') from None
    data=await request.body()
    mime=request.headers.get('content-type','').split(';')[0]
    if mime not in ('image/png','image/jpeg','image/webp'): raise HTTPException(415,'Use PNG, JPEG or WebP')
    try:
        with Image.open(io.BytesIO(data)) as original:
            if original.format not in ('PNG','JPEG','WEBP') or Image.MIME.get(original.format)!=mime: raise ValueError()
            if original.width*original.height>16_000_000 or max(original.size)>8192 or min(original.size)<1: raise ValueError()
            original.verify()
        with Image.open(io.BytesIO(data)) as original:
            image=ImageOps.exif_transpose(original).convert('RGB')
            width,height=image.size
            out=io.BytesIO();image.save(out,format='PNG');canonical=out.getvalue()
        if len(canonical)>MAX_BODY: raise ValueError()
        p=Prompts.model_validate_json(prompts)
        import math
        if any(not all(math.isfinite(v) for v in x) or not(0<=x[0]<=1 and 0<=x[1]<=1 and x[2] in (0,1)) for x in p.points): raise ValueError()
        if any(not all(math.isfinite(v) for v in x) or not(0<=x[0]<x[2]<=1 and 0<=x[1]<x[3]<=1) for x in p.boxes): raise ValueError()
    except (ValueError,ValidationError,UnidentifiedImageError,OSError,Image.DecompressionBombError): raise HTTPException(422,'invalid_image_or_prompts') from None
    if p.points and not state['point_prompts'] or p.boxes and not state['box_prompts']: raise HTTPException(422,'prompt_not_supported')
    response=await inference(request,'segmentation',canonical,'image/png',p.model_dump())
    try:
        from .geometry import from_geojson
        from shapely.geometry import box, mapping
        masks=response['masks']
        if not isinstance(masks,list) or not 1<=len(masks)<=8: raise ValueError()
        normalized=[]
        for mask in masks:
            raw=mask['geometry']; encoded=json.dumps(raw,allow_nan=False)
            if len(encoded)>64000: raise ValueError()
            g=from_geojson(raw)
            if not box(0,0,1,1).covers(g): raise ValueError()
            confidence=mask.get('confidence')
            if confidence is not None and (isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0<=confidence<=1): raise ValueError()
            normalized.append({'geometry':mapping(g),'confidence':confidence})
    except ImportError: raise HTTPException(503,'geometry_unavailable') from None
    except (KeyError,TypeError,ValueError): raise HTTPException(502,'invalid_segmentation_output') from None
    return {'status':'live_ai','width_px':width,'height_px':height,'masks':normalized,
            'provenance':{'provider':r.segmentation.provider,'model_id':r.segmentation.model,'source':'provider_prediction'}}

class RecommendationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    material_type:str=Field(default='unspecified',max_length=120)
    width_mm:float=Field(gt=0,allow_inf_nan=False)
    height_mm:float=Field(gt=0,allow_inf_nan=False)
    material_mm:dict
    preferences:str=Field(default='',max_length=1000)
    clearance_mm:float=Field(default=.5,ge=0,le=100,allow_inf_nan=False)
    grid_mm:float=Field(default=.5,gt=0,le=100,allow_inf_nan=False)

class CuttingIdeasInput(RecommendationInput):
    piece_width_mm:float=Field(ge=.1,le=1000,allow_inf_nan=False)
    piece_height_mm:float=Field(ge=.1,le=1000,allow_inf_nan=False)
    quantity:int=Field(ge=1,le=50,strict=True)

@router.post('/cutting-ideas')
async def cutting_ideas(request:Request,body:CuttingIdeasInput,use_ai:bool=True):
    """Public craft ideas are parameterized rectangles, never miniature fixtures."""
    from .layout_api import LayoutRequest,calculate
    from .geometry import from_geojson
    from shapely.geometry import box,mapping
    from .providers.baseten import validate_ranking
    try:
        material=from_geojson(body.material_mm)
        x,y,a,b=material.bounds
        if abs(a-x-body.width_mm)>1e-6 or abs(b-y-body.height_mm)>1e-6:raise ValueError()
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'dimensions_must_match_calibrated_geometry') from None
    from .cutting_options import verified_options,diverse_ideas,project_limitation
    feasible=await asyncio.to_thread(verified_options,material,body)
    limitation=project_limitation(body.preferences)
    state=runtime(request).availability('material_vision') # Same exact Baseten profile, no other providers.
    if not feasible or not state['available'] or not use_ai:
        reason='no_verified_fits' if not feasible else state['reason'] if not state['available'] else 'geometry_only_requested'
        return {'status':'deterministic_fallback','reason':reason,'ai_available':state['available'],'project_limitation':limitation,
                'ranked_projects':[],'options':feasible,'provenance':None}
    model_options=diverse_ideas(feasible)
    context={**body.model_dump(),'verified_templates':model_options,'project_limitation':limitation,
             'instruction':'Rank these different verified shape families. They are only square patches, narrow strips and wider rectangular panels. Never claim they make a complete garment, sleeve, neckline or finished project, and never claim a perfect fit for an unsupported project. Explain each as a practical cutting blank only. Do not infer dimensions or grain direction.'}
    response=await inference(request,'recommendation',context)
    try:ranking=validate_ranking(response,[o['project_id'] for o in model_options])
    except (KeyError,TypeError,ValueError):raise HTTPException(502,'invalid_recommendation_output') from None
    if limitation:
        descriptions={o['project_id']:o['description'] for o in model_options}
        # Preserve real model ordering, but do not display unsupported garment
        # claims from free-form text. These descriptions are explicitly app-authored.
        ranking=[{**item,'explanation':descriptions[item['project_id']]} for item in ranking]
    return {'status':'live_ai','ranked_projects':ranking,'options':model_options,'project_limitation':limitation,
            'explanation_source':'supported_operation_descriptions' if limitation else 'model',
            'provenance':{'provider':'baseten','model_id':runtime(request).recommendation.model}}

@router.post('/recommend')
async def recommend(request:Request, body:RecommendationInput):
    try:
        from .layout_api import TEMPLATES, LayoutRequest, calculate
        from .geometry import from_geojson
    except ImportError: raise HTTPException(503,'geometry_unavailable') from None
    try:
        material=from_geojson(body.material_mm)
        x,y,a,b=material.bounds
        if abs((a-x)-body.width_mm)>1e-6 or abs((b-y)-body.height_mm)>1e-6: raise ValueError()
    except (ValueError,KeyError,TypeError): raise HTTPException(422,'dimensions_must_match_calibrated_geometry') from None
    def feasible_templates():
        return [key for key in TEMPLATES if calculate(LayoutRequest(template_id=key,material_mm=body.material_mm,clearance_mm=body.clearance_mm,grid_mm=body.grid_mm))['status']=='success']
    feasible=await asyncio.to_thread(feasible_templates)
    r=runtime(request); state=r.availability('recommendation')
    fallback=[{'project_id':k,'explanation':'Deterministic geometry check found a complete verified fit.'} for k in feasible]
    if not feasible or not state['available']:
        return {'status':'deterministic_fallback','reason':state['reason'] or 'no_verified_fits','ranked_projects':fallback,'provenance':None}
    context={**body.model_dump(),'verified_templates':[{'project_id':k,**TEMPLATES[k]} for k in feasible]}
    response=await inference(request,'recommendation',context)
    try:
        from .providers.baseten import validate_ranking
        result=validate_ranking(response,feasible)
    except (KeyError,TypeError,ValueError): raise HTTPException(502,'invalid_recommendation_output') from None
    return {'status':'live_ai','ranked_projects':result,'provenance':{'provider':r.recommendation.provider,'model_id':r.recommendation.model}}
