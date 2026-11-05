import json
from pathlib import Path
from .environment import load_environment
load_environment()
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
app=FastAPI(title='MakeFromThis Stage 01')
DATA=json.loads((Path(__file__).parent/'scenes.json').read_text())
PUBLIC_DATA=json.loads((Path(__file__).parent/'public-scenes.json').read_text())
class Scene(BaseModel):
 kind:str='synthetic'
 annotation_source:str='synthetic_ground_truth'
 scale_status:str='synthetic'
 thumbnail:str | None=None
 annotation_provenance:dict | None=None
 illustrative_mm_per_pixel:float | None=None
 title:str=''
 description:str=''
 featured:bool=False
 presentation_order:int=999
 expected_fit:str='verify_with_solver'
 # Full pixel-space GeoJSON is authoritative for disconnected material/holes.
 # polygon_px remains the first exterior ring for older consumers.
 geometry_px:dict | None=None
 id:str; source:str; image:str; width_px:int; height_px:int; mm_per_pixel:float | None
 mask:str | None=None
 polygon_px:list[list[int]]=Field(default_factory=list)
@app.get('/health')
def health(): return {'status':'ok'}
@app.get('/api/demo-scenes',response_model=list[Scene])
def scenes():
 # Regression fixtures remain addressable for reproducibility, never gallery choices.
 return [s for s in PUBLIC_DATA if s.get('kind')=='photograph'
         and s.get('annotation_source')=='manual_required' and s.get('gallery_visible',True)
         and not s.get('mask') and not s.get('geometry_px') and not s.get('polygon_px')
         and not s.get('annotation_provenance') and s.get('mm_per_pixel') is None]
@app.get('/api/demo-scenes/{scene_id}',response_model=Scene)
def scene(scene_id:str):
 for s in PUBLIC_DATA+DATA:
  if s['id']==scene_id:return s
 raise HTTPException(404,'Scene not found')

# Stage 02: optional local geometry endpoints; Stage 01 routes remain unchanged.
try:
 from .layout_api import router as layout_router
except ModuleNotFoundError as exc:
 if exc.name != 'shapely':
  raise
 # Stage 01 remains available if the optional Stage 02 dependency is absent.
 @app.get('/api/project-templates')
 @app.get('/api/demo-scenes/{scene_id}/material')
 @app.post('/api/layouts')
 @app.post('/api/layouts/svg')
 def geometry_unavailable():
  raise HTTPException(503, 'Stage 02 requires Shapely; install backend/requirements.txt')
else:
 app.include_router(layout_router)

# Stage 04: inert unless explicitly configured and enabled.
from .ai_api import router as ai_router, BodyLimit
from .providers.core import Runtime
app.state.ai_runtime = Runtime()
app.add_middleware(BodyLimit)
app.include_router(ai_router)

# Register static fallback last, after all API routes.
from .release import configure
configure(app)
