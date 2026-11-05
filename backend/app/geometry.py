"""Stage 02 geometry, authored for MakeFromThis / Meta Global AI Developer Hackathon.

SVG support is intentionally limited to the binary rect/polygon masks generated
by Stage 01. Unsupported SVG constructs fail closed; there is no raster tracing.
"""
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from shapely import affinity
from shapely.geometry import Polygon, MultiPolygon, box, shape, mapping
from shapely.errors import GEOSException


def valid_material(geometry):
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise ValueError('Material must be Polygon or MultiPolygon')
    coordinates = mapping(geometry)['coordinates']
    def finite(value):
        return all(finite(v) for v in value) if isinstance(value, (list, tuple)) else math.isfinite(value)
    if not finite(coordinates) or geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError('Geometry must be finite, nonempty and valid, with positive area')
    return geometry


def from_geojson(data):
    # The web app submits coordinates, never uploaded image bytes. Fail malformed
    # GeoJSON closed before it reaches GEOS; valid Stage 02 inputs are unchanged.
    if not isinstance(data, dict) or data.get('type') not in ('Polygon', 'MultiPolygon') or not isinstance(data.get('coordinates'), (list, tuple)):
        raise ValueError('Expected GeoJSON Polygon or MultiPolygon coordinates')
    # Bound untrusted geometry complexity before constructing GEOS objects.
    stack=[(data['coordinates'],0)]; vertices=0
    while stack:
        value,depth=stack.pop()
        if depth>5 or not isinstance(value,(list,tuple)):
            raise ValueError('Invalid coordinate structure')
        if value and isinstance(value[0],(int,float)):
            if len(value)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1_000_000 for v in value):
                raise ValueError('Coordinates must be finite 2D values within one million units')
            vertices+=1
            if vertices>2048:raise ValueError('Geometry exceeds 2048 vertices')
        else:
            if len(value)>2048:raise ValueError('Geometry exceeds complexity budget')
            stack.extend((child,depth+1) for child in value)
    try:
        return valid_material(shape(data))
    except (KeyError, IndexError, TypeError, GEOSException) as exc:
        raise ValueError('Invalid polygon coordinates') from exc


def mask_to_mm(path: Path, mm_per_pixel: float):
    if not math.isfinite(mm_per_pixel) or mm_per_pixel <= 0:
        raise ValueError('Scale must be positive and finite')
    root = ET.parse(path).getroot()
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Expected SVG mask')
    if set(root.attrib) - {'width', 'height', 'viewBox'}:
        raise ValueError('Unsupported SVG root attributes')
    width, height = float(root.attrib['width']), float(root.attrib['height'])
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('Invalid mask dimensions')
    if 'viewBox' in root.attrib and root.attrib['viewBox'].split() != ['0', '0', str(int(width)), str(int(height))]:
        raise ValueError('Mask viewBox must match pixel dimensions')
    result = Polygon()
    for element in root:
        tag = element.tag.rsplit('}', 1)[-1]
        allowed = {'fill', 'x', 'y', 'width', 'height'} if tag == 'rect' else {'fill', 'points'}
        if tag not in ('rect', 'polygon') or set(element.attrib) - allowed:
            raise ValueError('Only untransformed binary SVG rect/polygon masks are supported')
        fill = element.attrib.get('fill')
        if fill not in ('black', 'white'):
            raise ValueError('Mask must use binary black/white fills')
        if tag == 'rect':
            x, y = float(element.get('x', '0')), float(element.get('y', '0'))
            w, h = float(element.get('width', '0')), float(element.get('height', '0'))
            if w <= 0 or h <= 0:
                raise ValueError('Invalid rectangle')
            geom = box(x, y, x + w, y + h)
        else:
            numbers = [float(v) for v in re.split(r'[\s,]+', element.attrib['points'].strip())]
            if len(numbers) < 6 or len(numbers) % 2:
                raise ValueError('Invalid polygon points')
            geom = Polygon(list(zip(numbers[::2], numbers[1::2])))
        valid_material(geom)
        geom = geom.intersection(box(0, 0, width, height))
        result = result.union(geom) if fill == 'white' else result.difference(geom)
    return valid_material(affinity.scale(result, xfact=mm_per_pixel, yfact=mm_per_pixel, origin=(0, 0)))
