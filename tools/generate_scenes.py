"""Deterministic presentation scenes, authored for MakeFromThis hackathon work.

Standard-library only. Geometry is explicit integer pixels, not traced from a
photograph. Images and binary masks share the same rings without approximation.
"""
import json
import math
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 400, 280


def closed(ring):
    return [list(p) for p in ring] + [list(ring[0])]


def geometry(polygons):
    coords = [[closed(r) for r in rings] for rings in polygons]
    return {'type': 'Polygon', 'coordinates': coords[0]} if len(coords) == 1 else {'type': 'MultiPolygon', 'coordinates': coords}


def svg_path(polygons):
    return ' '.join('M' + ' L'.join(f'{x},{y}' for x,y in ring) + ' Z' for rings in polygons for ring in rings)


def points(ring):
    return ' '.join(f'{x},{y}' for x,y in ring)


PRESENTATION = [
    dict(title='Cardboard offcut', description='Large irregular cardboard silhouette with procedural corrugation.',
         color='#bd945c', ink='#79572f', texture='cardboard', polygons=[[[[26,42],[236,22],[368,64],[352,196],[280,252],[72,238],[30,166]]]]),
    dict(title='Notched fabric', description='Concave fabric silhouette: the deep notch is unavailable material.',
         color='#75939a', ink='#365a64', texture='woven', polygons=[[[[30,32],[365,28],[370,105],[246,108],[246,172],[340,174],[321,252],[36,246],[58,159],[24,130]]]]),
    dict(title='Three separate scraps', description='Three disconnected pieces; placements must stay within real material, never bridge gaps.',
         color='#ba8470', ink='#784c40', texture='speckled', polygons=[
             [[[26,32],[157,28],[155,135],[36,146]]],
             [[[210,26],[366,40],[350,146],[214,128]]],
             [[[100,182],[280,168],[340,240],[126,252]]]]),
    dict(title='Sheet with a cutout', description='A large internal rectangular hole is excluded from all usable-area and fit calculations.',
         color='#88a078', ink='#486541', texture='felt', polygons=[[
             [[28,30],[355,26],[374,226],[332,252],[24,238]],
             [[145,86],[260,86],[260,192],[145,192]]]]),
    dict(title='Asymmetrical sheet', description='Broad asymmetric sheet with angled cuts and an uneven lower edge.',
         color='#c9aa7a', ink='#85623a', texture='diagonal', polygons=[[[[28,42],[205,24],[362,82],[338,132],[370,216],[234,248],[178,213],[50,252],[38,160]]]]),
    dict(title='Narrow frame challenge', description='Infeasible at 0.5 mm edge clearance: the 0.72 mm border leaves no usable interior.',
         color='#ad777e', ink='#783e4e', texture='woven', expected_fit='infeasible_at_default_clearance', polygons=[[
             [[24,30],[376,30],[376,250],[24,250]],
             [[42,48],[358,48],[358,232],[42,232]]]]),
]


def texture(kind, polygons, ink):
    """Portable explicit SVG marks; no external files or pattern-fill support.

    Scanline intersections generate marks inside even-odd material intervals.
    Sparse dots/fibres are kept away from boundaries; the final SVG clip is exact.
    """
    rings=[ring for poly in polygons for ring in poly]
    marks=[]
    for axis in ([0,1] if kind=='woven' else [0]):
        for fixed in range(4,HEIGHT if axis==0 else WIDTH,6):
            crossings=[]
            for ring in rings:
                for (x1,y1),(x2,y2) in zip(ring,ring[1:]+ring[:1]):
                    a,b=(y1,y2) if axis==0 else (x1,x2)
                    c,d=(x1,x2) if axis==0 else (y1,y2)
                    if min(a,b)<=fixed<max(a,b):crossings.append(c+(fixed-a)*(d-c)/(b-a))
            crossings.sort()
            for left,right in zip(crossings[::2],crossings[1::2]):
                if kind in ('cardboard','woven'):
                    marks.append(f'M{left:.3f},{fixed}H{right:.3f}' if axis==0 else f'M{fixed},{left:.3f}V{right:.3f}')
                else:
                    for position in range(math.ceil(left+4),math.floor(right-4),12):
                        x,y=position,fixed
                        # At least four pixels from any edge keeps tiny marks inside.
                        distances=[]
                        for ring in rings:
                            for (ax,ay),(bx,by) in zip(ring,ring[1:]+ring[:1]):
                                dx,dy=bx-ax,by-ay
                                t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
                                distances.append(math.hypot(x-ax-t*dx,y-ay-t*dy))
                        if min(distances)<4:continue
                        if kind=='speckled':marks.append(f'M{x},{y}h.7')
                        elif kind=='felt':marks.append(f'M{x},{y}l2,1')
                        else:marks.append(f'M{x},{y}l2,-2')
    return f'<path d="{" ".join(marks)}" fill="none" stroke="{ink}" stroke-width=".8" stroke-linecap="round" opacity=".28" clip-path="url(#material-clip)"/>'


def generate():
    folder = ROOT/'public/scenes'; folder.mkdir(parents=True, exist_ok=True)
    scenes = []
    for i in range(12):
        scene_id = f'scene-{i+1:02}'
        if i < len(PRESENTATION):
            spec = PRESENTATION[i]; scale = .04
        else:
            # Retain six small baseline fixtures and their IDs behind the showcase.
            x=30+(i%4)*90; y=30+(i//4)*85; w=45+(i%3)*5; h=35+(i%2)*8
            spec=dict(title=f'Regression sample {i+1:02}',description='Small synthetic baseline retained for comparison.',
                      color='#b4b2a2',ink='#6e6d5f',texture='diagonal',
                      polygons=[[[[x,y],[x+w,y+4],[x+w-5,y+h],[x+3,y+h-3]]]])
            scale=.25
        polygons=spec['polygons']; path=svg_path(polygons)
        image=f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="280" viewBox="0 0 400 280">
<title>{escape(spec['title'])} — synthetic material visualization</title>
<desc>{escape(spec['description'])} Original procedural texture, not a photograph.</desc>
<defs><clipPath id="material-clip"><path d="{path}" clip-rule="evenodd"/></clipPath></defs>
<rect width="400" height="280" fill="#eeeae2"/>
<path data-material="true" d="{path}" fill="{spec['color']}" fill-rule="evenodd" stroke="{spec['ink']}" stroke-width="1.3"/>
{texture(spec['texture'],polygons,spec['ink'])}
<text x="16" y="273" fill="#666052" font-family="sans-serif" font-size="9" letter-spacing="1.2">SYNTHETIC / {escape(spec['title'].upper())}</text>
</svg>'''
        # SVG painter order: white outer rings, then black holes. No strokes or
        # antialiased raster approximations are used to derive the ground truth.
        mask_shapes=[]
        for rings in polygons:
            for j,ring in enumerate(rings):
                mask_shapes.append(f'<polygon points="{points(ring)}" fill="{"white" if j==0 else "black"}"/>')
        mask='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="280"><rect width="400" height="280" fill="black"/>'+''.join(mask_shapes)+'</svg>'
        (folder/f'{scene_id}.svg').write_text(image,encoding='utf-8')
        (folder/f'{scene_id}-mask.svg').write_text(mask,encoding='utf-8')
        scenes.append(dict(id=scene_id,title=spec['title'],description=spec['description'],featured=i<6,presentation_order=i,
            expected_fit=spec.get('expected_fit','verify_with_solver'),
            source='synthetic (MakeFromThis explicit polygon generator v2; original procedural SVG texture; no photographic dataset)',
            image=f'/scenes/{scene_id}.svg',mask=f'/scenes/{scene_id}-mask.svg',width_px=WIDTH,height_px=HEIGHT,mm_per_pixel=scale,
            polygon_px=polygons[0][0],geometry_px=geometry(polygons)))
    real_path=ROOT/'backend/app/ctvg-scenes.json'
    real=json.loads(real_path.read_text()) if real_path.exists() else []
    (ROOT/'backend/app/scenes.json').write_text(json.dumps(real+scenes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Self-contained contact sheet for review; IDs are unique across nested SVGs.
    cards=[]
    for index,scene in enumerate(scenes[:6]):
        x=20+(index%2)*420; y=70+(index//2)*320
        source=(folder/f"{scene['id']}.svg").read_text(encoding='utf-8')
        source=source.replace('id="material-clip"',f'id="material-clip-{index}"').replace('url(#material-clip)',f'url(#material-clip-{index})')
        source=source[source.index('>')+1:source.rindex('</svg>')]
        source=f'<g transform="translate({x} {y})">'+source+'</g>'
        cards.append(source+f'<text x="{x}" y="{y+300}" font-family="sans-serif" font-size="15" fill="#25362e">{scene["id"]} / {escape(scene["title"])}</text>')
    sheet='<svg xmlns="http://www.w3.org/2000/svg" width="860" height="1040" viewBox="0 0 860 1040"><rect width="860" height="1040" fill="#f7f7f2"/><text x="20" y="30" font-family="sans-serif" font-size="21" fill="#25362e">MakeFromThis / synthetic material studies</text><text x="20" y="51" font-family="sans-serif" font-size="12" fill="#59665d">Explicit polygon ground truth. Original procedural textures. No photographic provenance.</text>'+''.join(cards)+'</svg>'
    (ROOT/'docs/presentation-scenes.svg').write_text(sheet,encoding='utf-8')



if __name__ == '__main__':
    generate()
