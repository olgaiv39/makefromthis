"""Stage 02 local geometry API. No models, network calls or optimization service."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import Polygon, mapping
from shapely.errors import GEOSException
from .geometry import from_geojson, mask_to_mm
from .nesting import nest, svg_layout

ROOT = Path(__file__).resolve().parents[2]
SCENES = json.loads((Path(__file__).parent / 'scenes.json').read_text())
# Small geometry demonstrators sized for the synthetic material scenes (roughly 10 mm).
# These are cutting shapes, not claims of full-size functional garments/products.
TEMPLATES = {
    'square-tabs': {'name': 'Two square tabs', 'parts': [[[0,0],[2,0],[2,2],[0,2]]] * 2},
    'triangle-markers': {'name': 'Three triangular markers', 'parts': [[[0,0],[2,0],[0,2]]] * 3},
    'corner-pieces': {'name': 'Two L-shaped corners', 'parts': [[[0,0],[3,0],[3,1],[1,1],[1,3],[0,3]]] * 2},
}
router = APIRouter(prefix='/api')

class LayoutRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scene_id: str = 'scene-01'
    template_id: str = 'square-tabs'
    clearance_mm: float = Field(default=0.5, ge=0, le=100, allow_inf_nan=False)
    grid_mm: float = Field(default=0.5, gt=0, le=100, allow_inf_nan=False)
    scene_mm_per_pixel: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    scene_scale_mode: str | None = None
    source_scene_id: str | None = None
    # Optional custom GeoJSON material and parts, always expressed in millimeters.
    material_mm: dict | None = None
    parts_mm: list[dict] | None = Field(default=None, min_length=1, max_length=50)


def scene_material(scene_id, mm_per_pixel=None, scale_mode=None):
    scene = next((s for s in SCENES if s['id'] == scene_id), None)
    if scene is None:
        raise HTTPException(404, 'Scene not found')
    scale=scene['mm_per_pixel']
    if scene.get('kind')=='photograph':
        if mm_per_pixel is None or scale_mode not in ('illustrative','user_calibrated'):
            raise HTTPException(422, 'physical_scale_required: supply scene_mm_per_pixel and scene_scale_mode (illustrative or user_calibrated)')
        scale=mm_per_pixel
    return scene, mask_to_mm(ROOT / 'public' / scene['mask'].lstrip('/'), scale)


@router.get('/project-templates')
def templates():
    return [{'id': key, 'name': t['name'], 'units': 'mm',
             'description': 'Synthetic miniature geometry demonstrator',
             'parts': [mapping(Polygon(p)) for p in t['parts']]} for key,t in TEMPLATES.items()]


@router.get('/demo-scenes/{scene_id}/material')
def material(scene_id: str):
    s=next((s for s in SCENES if s['id']==scene_id),None)
    if s is None:raise HTTPException(404,'Scene not found')
    if s.get('kind')=='photograph':
        g=from_geojson(s['geometry_px'])
        return {'scene_id':scene_id,'source':s['source'],'units':'px','mm_per_pixel':None,
                'scale_status':'uncalibrated','geometry':mapping(g),'area_px2':g.area,
                'annotation_provenance':s['annotation_provenance']}
    s, geom = scene_material(scene_id)
    return {'scene_id': scene_id, 'source': s['source'], 'units': 'mm',
            'mm_per_pixel': s['mm_per_pixel'], 'geometry': mapping(geom), 'area_mm2': geom.area}


def calculate(request):
    try:
        if request.material_mm is not None:
            geom = from_geojson(request.material_mm)
            source = 'User-supplied geometry in millimeters'
        else:
            s, geom = scene_material(request.scene_id,request.scene_mm_per_pixel,request.scene_scale_mode)
            source = s['source']
        if request.parts_mm is not None:
            parts = {f'part-{i+1:02}': from_geojson(p) for i,p in enumerate(request.parts_mm)}
        else:
            if request.template_id not in TEMPLATES:
                raise HTTPException(404, 'Project template not found')
            parts = {f'part-{i+1:02}': Polygon(p) for i,p in enumerate(TEMPLATES[request.template_id]['parts'])}
        import math
        def count(g):
            polygons=[g] if g.geom_type=='Polygon' else g.geoms
            return sum(len(p.exterior.coords)+sum(len(r.coords) for r in p.interiors) for p in polygons)
        x,y,a,b=geom.bounds
        trials=(math.floor((a-x)/request.grid_mm)+1)*(math.floor((b-y)/request.grid_mm)+1)*len(parts)*4
        if trials*(count(geom)+sum(count(p) for p in parts.values()))>10_000_000:
            raise ValueError('Geometry work budget exceeded; increase grid_mm or simplify outlines')
        result = nest(geom, parts, request.clearance_mm, request.grid_mm)
        result.update(source=source, units='mm')
        requested_area=sum(p.area for p in parts.values())
        bounds_too_small=any(not ((p.bounds[2]-p.bounds[0]+2*request.clearance_mm<=a-x and p.bounds[3]-p.bounds[1]+2*request.clearance_mm<=b-y)
            or (p.bounds[3]-p.bounds[1]+2*request.clearance_mm<=a-x and p.bounds[2]-p.bounds[0]+2*request.clearance_mm<=b-y)) for p in parts.values())
        code='complete' if result['status']=='success' else 'part_exceeds_material_bounds' if bounds_too_small else 'requested_area_exceeds_material_area' if requested_area>geom.area else 'heuristic_incomplete'
        result['fit_diagnostics']={'code':code,'width_mm':a-x,'height_mm':b-y,'requested_area_mm2':requested_area,
            'requested_count':len(parts),'placed_count':len(result['placements']),'grid_mm':request.grid_mm,'clearance_mm':request.clearance_mm}
        if request.material_mm is None and s.get('kind')=='photograph':
            result.update(annotation_source='dataset_ground_truth',scale_status=request.scene_scale_mode, mm_per_pixel=request.scene_mm_per_pixel,
                          physically_calibrated=request.scene_scale_mode=='user_calibrated',
                          scale_note='Illustrative dimensions, NOT measured from the dataset.' if request.scene_scale_mode=='illustrative' else 'Scale supplied by user; not a dataset measurement.',
                          annotation_provenance=s['annotation_provenance'])
        if request.material_mm is not None and request.source_scene_id:
            original=next((item for item in SCENES if item['id']==request.source_scene_id and item.get('kind')=='photograph'),None)
            if original is None:raise HTTPException(404,'Source photograph not found')
            result.update(annotation_provenance=original['annotation_provenance'],annotation_source='custom_outline',source='Custom outline on a CTVG photograph; original dataset annotation retained for attribution')
        if request.material_mm is not None and request.scene_scale_mode=='illustrative':
            result.update(scale_status='illustrative',physically_calibrated=False,scale_note='Illustrative dimensions, NOT measured from the dataset.')
        return result
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, OverflowError, GEOSException) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/layouts')
def layout(request: LayoutRequest):
    return calculate(request)


@router.post('/layouts/svg')
def cutting_svg(request: LayoutRequest):
    result = calculate(request)
    if result['status'] != 'success':
        raise HTTPException(422, result)
    svg=svg_layout(result)
    if result.get('scale_status')=='illustrative':
        svg=svg.replace('<title>', '<desc>ILLUSTRATIVE SCALE ONLY. Not physically calibrated; do not use these mm dimensions as measured garment dimensions.</desc><title>Illustrative scale — ')
    if result.get('annotation_provenance'):
        from html import escape
        p=result['annotation_provenance']
        attribution='CTVG: '+', '.join(p['authors'])+'; DOI '+p['doi']+'; CC BY 4.0 https://creativecommons.org/licenses/by/4.0/; source '+p['source_annotation']+'; modified to a cutting layout; '+result.get('scale_note','User-supplied scale.')
        svg=svg.replace('<title>', '<metadata>'+escape(attribution)+'</metadata><title>',1)
    return Response(svg, media_type='image/svg+xml')
