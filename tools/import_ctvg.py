"""Import four CC BY 4.0 CTVG real photographs; never extract the whole archive.

Run with backend Shapely/Pillow installed. Source JPEG/JSON bytes are preserved.
Original application integration code; dataset assets remain third-party data.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile
from PIL import Image
from shapely.geometry import Polygon, MultiPolygon, mapping

ROOT=Path(__file__).resolve().parents[1]
PREFIX='CTVG/all_448/real/black/'
SAMPLES=[('ctvg-01','Blouse sleeve','blouse/jersey_plain_purple/0000'),
         ('ctvg-02','Shirt panel','shirt/taffeta_polyester_green/0000'),
         ('ctvg-03','Dress piece','dress/poplin_cotton_mix/0028'),
         ('ctvg-04','Shorts piece','shorts/poplin_cotton_mix/0008')]
ATTRIBUTION={'dataset':'CTVG — Cut Textile Garment Pieces','version':1,
 'authors':['Daniel Costa','João Cruz','Gualter Barros','Nelson Rodrigues'],
 'doi':'10.17632/m5wds8287s.1','url':'https://data.mendeley.com/datasets/m5wds8287s/1',
 'license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/'}


def digest(data):return hashlib.sha256(data).hexdigest()


def annotation_geometry(label):
    image=label['image'];polygons=[]
    if image['width']!=448 or image['height']!=448 or image['n_polygons']!=len(image['polygons']):raise ValueError('Unexpected CTVG dimensions/count')
    for item in image['polygons']:
        ring=item['segmentation']
        if not isinstance(ring,list) or len(ring)<3 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,int) or not 0<=v<448 for v in p) for p in ring):
            raise ValueError('Unsupported CTVG contour; do not flatten or repair annotations')
        polygon=Polygon(ring)
        if polygon.is_empty or not polygon.is_valid or polygon.area<=0:raise ValueError('Invalid source topology')
        polygons.append(polygon)
    result=polygons[0] if len(polygons)==1 else MultiPolygon(polygons)
    if not result.is_valid:raise ValueError('Source polygons overlap/touch incompatibly')
    return result


def build_sample(scene_id,title,stem,jpeg,raw_label,output):
    label=json.loads(raw_label);geom=annotation_geometry(label);image_info=label['image']
    expected='real/black/'+stem+'.jpeg'
    if image_info['filepath']!=expected:raise ValueError('Image/annotation pairing mismatch')
    with Image.open(io.BytesIO(jpeg)) as image:
        if image.format!='JPEG' or image.size!=(448,448):raise ValueError('Unexpected source photo')
        if image.getexif().get(274,1)!=1:raise ValueError('Source orientation would need explicit coordinate transform')
        x,y,a,b=geom.bounds
        crop=(max(0,int(x)-16),max(0,int(y)-16),min(448,int(a)+17),min(448,int(b)+17))
        thumb=image.convert('RGB').crop(crop);thumb.thumbnail((224,224))
        thumb.save(output/f'{scene_id}-thumb.webp',format='WEBP',quality=82,method=6)
    (output/f'{scene_id}.jpeg').write_bytes(jpeg)
    (output/f'{scene_id}.json').write_bytes(raw_label)
    paths=[]
    for item in image_info['polygons']:
        paths.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in item['segmentation'])+'" fill="white"/>')
    mask='<svg xmlns="http://www.w3.org/2000/svg" width="448" height="448"><rect width="448" height="448" fill="black"/>'+''.join(paths)+'</svg>'
    (output/f'{scene_id}-mask.svg').write_text(mask)
    return dict(id=scene_id,title='CTVG · '+title,description='Real textile photograph with dataset-provided contour. No physical scale supplied; not a SAM prediction.',
        kind='photograph',annotation_source='dataset_ground_truth',scale_status='uncalibrated',
        featured=True,presentation_order=-10+int(scene_id[-2:]),expected_fit='requires_explicit_scale',
        source='CTVG real photograph; dataset-provided ground-truth contour; CC BY 4.0; no AI segmentation',
        image=f'/ctvg/{scene_id}.jpeg',thumbnail=f'/ctvg/{scene_id}-thumb.webp',mask=f'/ctvg/{scene_id}-mask.svg',
        width_px=448,height_px=448,mm_per_pixel=None,illustrative_mm_per_pixel=.06,
        polygon_px=image_info['polygons'][0]['segmentation'],geometry_px=mapping(geom),
        annotation_provenance={**ATTRIBUTION,'source_image':PREFIX+stem+'.jpeg','source_annotation':PREFIX+stem+'.json',
            'source_image_sha256':digest(jpeg),'source_annotation_sha256':digest(raw_label),
            'annotation_url':f'/ctvg/{scene_id}.json','polygon_ids':[p['id'] for p in image_info['polygons']],
            'polygon_labels':[p['label'] for p in image_info['polygons']],
            'modifications':'Original JPEG/JSON unchanged. Closed rings for GeoJSON; binary SVG mask derived from contours. Cropped/resized WebP thumbnail only; full photo/coordinates unchanged.',
            'thumbnail_crop_px':crop})


def import_archive(archive,root=ROOT):
    output=root/'public/ctvg';output.mkdir(parents=True,exist_ok=True)
    records=[]
    with ZipFile(archive) as z:
        for scene_id,title,stem in SAMPLES:
            records.append(build_sample(scene_id,title,stem,z.read(PREFIX+stem+'.jpeg'),z.read(PREFIX+stem+'.json'),output))
    (root/'backend/app/ctvg-scenes.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    manifest=root/'backend/app/scenes.json'
    synthetic=[s for s in json.loads(manifest.read_text()) if s['id'].startswith('scene-')]
    if len(synthetic)!=12:raise ValueError('Expected all 12 synthetic regression fixtures')
    manifest.write_text(json.dumps(records+synthetic,ensure_ascii=False,indent=2)+'\n')
    (output/'ATTRIBUTION.md').write_text('''# CTVG real photographic demonstration assets

Daniel Costa, João Cruz, Gualter Barros and Nelson Rodrigues (2024), CTVG,
Mendeley Data, v1, DOI: https://doi.org/10.17632/m5wds8287s.1
Source: https://data.mendeley.com/datasets/m5wds8287s/1
License: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/

Only four source JPEG/JSON pairs from all_448/real/black/ are redistributed.
Original photographs/annotations remain unchanged. Original coordinates are
retained; contours are closed for GeoJSON and converted to binary SVG masks.
Gallery WebP thumbnails are cropped/resized/re-encoded; full images are untouched.
No physical scale is provided. Any demonstration mm dimensions are explicitly
illustrative until a real measurement is supplied. These are not SAM predictions.
No endorsement by the dataset authors is implied. See docs/DATA_SOURCES.md.
''',encoding='utf-8')
    return records

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args()
    records=import_archive(args.archive)
    print('Imported',len(records),'official real photo/annotation pairs; all 12 synthetic fixtures retained.')
