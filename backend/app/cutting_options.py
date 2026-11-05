"""Bounded rectangle/square alternatives, verified by the existing nesting engine."""
import math
import re
from shapely.geometry import box,mapping

MAX_CHECKS=12
MAX_RESULTS=6

def shape_kind(width,height):
    short,long=sorted((width,height))
    return 'square_patch' if abs(long-short)<.01 else 'narrow_strip' if long/short>=3 else 'fabric_panel'

DESCRIPTIONS={
    'square_patch':'Square patches for fabric decoration or patchwork practice.',
    'narrow_strip':'Narrow rectangular strips for trim or binding experiments; include any needed seam allowance.',
    'fabric_panel':'Wider rectangular panels for seam practice or planning a custom pattern.'}

def project_limitation(preferences):
    if re.search(r'\b(t[\s-]?shirt|shirt|dress|sleeves?|hoodie|blouse|trousers|garment|neckline|curved|circle)\b',preferences,re.I):
        return ('This tool cuts rectangles and squares, not a complete garment or curved pattern. '
                'A t-shirt needs a neckline, sleeves and construction details. These are patches, strips or panels for experimentation, not finished garment pieces.')
    return None

def diverse_ideas(options):
    """One verified physical design per shape family, rather than quantity repeats."""
    result=[]
    for kind in ('square_patch','narrow_strip','fabric_panel'):
        group=[o for o in options if o['shape_kind']==kind]
        if group:result.append(max(group,key=lambda o:(o['width_mm']*o['height_mm'],o['quantity'])))
    return result

def vertex_count(material):
    polygons=[material] if material.geom_type=='Polygon' else material.geoms
    return sum(len(p.exterior.coords)+sum(len(r.coords) for r in p.interiors) for p in polygons)

def safe_grid(material,count,preferred):
    x,y,a,b=material.bounds;w,h=a-x,b-y
    cells=min(30000/(4*count),3000000/(4*count*(vertex_count(material)+5*count)))
    def allowed(step):return (math.floor(w/step)+1)*(math.floor(h/step)+1)<=cells
    step=max(.5,min(preferred,max(w,h)/80))
    if not allowed(step):
        lo,hi=step,max(step,w,h)
        for _ in range(40):
            mid=(lo+hi)/2
            if allowed(mid):hi=mid
            else:lo=mid
        step=hi
    return math.ceil(step*10)/10

def verified_options(material,body):
    from .layout_api import LayoutRequest,calculate
    x,y,a,b=material.bounds;w,h=a-x,b-y;gap=body.clearance_mm
    usable=material.buffer(-gap) if gap else material
    if usable.is_empty:return []
    requested=body.quantity;pw,ph=body.piece_width_mm,body.piece_height_mm
    context=(body.material_type+' '+body.preferences).lower()
    textile=any(word in context for word in ('fabric','cotton','felt','patchwork','quilt'))
    generated_minimum=10 if textile else 5
    pool=[];seen=set()
    def add(key,width,height,quantity):
        width,height=round(width,1),round(height,1);quantity=max(1,min(50,int(quantity)))
        value=(*sorted((width,height)),quantity)
        if value in seen or min(width,height)<5 or max(width,height)>1000:return
        if key!='rectangles' and min(width,height)<generated_minimum:return
        kind=shape_kind(width,height)
        seen.add(value);pool.append({'project_id':key,'width_mm':width,'height_mm':height,'quantity':quantity,
                                    'shape_kind':kind,'description':DESCRIPTIONS[kind]})
    def snapped(value):return math.floor(value/5)*5
    short,long=sorted((w-2*gap,h-2*gap))
    square=min(30,snapped(short*.35))
    strip_w=min(60,snapped(long*.6));strip_h=max(generated_minimum,min(15,snapped(short*.18)))
    panel_w=min(60,snapped(long*.55));panel_h=min(40,snapped(short*.4))
    add('rectangles',pw,ph,requested)
    add('patchwork-squares',square,square,min(requested,4))
    add('narrow-strips',strip_w,strip_h,min(requested,4))
    add('fabric-panels',panel_w,panel_h,min(requested,2))
    if requested>1:add('fewer-rectangles',pw,ph,min(2,requested-1));add('single-rectangle',pw,ph,1)
    add('smaller-rectangles',pw/2,ph/2,min(requested,8))
    add('single-patch',square,square,1);add('single-strip',strip_w,strip_h,1);add('single-panel',panel_w,panel_h,1)
    add('compact-squares',snapped(short*.2),snapped(short*.2),min(requested,4))
    add('single-small-blank',min(20,math.floor((w-2*gap)*.4/5)*5),min(15,math.floor((h-2*gap)*.4/5)*5),1)
    results=[]
    for option in pool[:MAX_CHECKS]:
        pw,ph,n=option['width_mm'],option['height_mm'],option['quantity']
        equivalent=next((o for o in results if sorted((o['width_mm'],o['height_mm']))==sorted((pw,ph))),None)
        if equivalent and equivalent['quantity']>=n:continue
        # Necessary bounds/area checks save CPU; they never establish a fit.
        if not ((pw+2*gap<=w and ph+2*gap<=h) or (ph+2*gap<=w and pw+2*gap<=h)):continue
        if pw*ph*n>usable.area:continue
        grid=safe_grid(material,n,body.grid_mm)
        if grid>100:continue
        result=calculate(LayoutRequest(template_id='custom-rectangles',parts_mm=[mapping(box(0,0,pw,ph)) for _ in range(n)],
            material_mm=body.material_mm,clearance_mm=gap,grid_mm=grid,scene_scale_mode='user_calibrated'))
        if result['status']=='success' and result['verification']['valid']:
            if equivalent:results.remove(equivalent)
            results.append({**option,'grid_mm':grid,'clearance_mm':gap,'verified':True})
        if len(results)>=MAX_RESULTS:break
    return results
