"""Deterministic bounded grid heuristic with independent verification, in mm."""
import math
from html import escape
from shapely import affinity
from shapely.geometry import Polygon, mapping
from .geometry import valid_material

ROTATIONS = (0, 90, 180, 270)
MAX_CANDIDATES = 250_000


def oriented(polygon, angle):
    p = affinity.rotate(polygon, angle, origin=(0, 0))
    x, y, _, _ = p.bounds
    return affinity.translate(p, -x, -y)


def verify(material, expected, placements, clearance):
    """Reconstruct placements from declared transforms; check shape, count and distances.

    No nesting candidate/filter functions are called here. Clearance means minimum
    Euclidean distance from every other part AND from all material boundaries.
    """
    valid_material(material)
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError('Clearance must be finite and nonnegative')
    errors, placed, seen = [], [], set()
    for placement in placements:
        key = placement['id']
        if key not in expected or key in seen:
            errors.append('Unexpected or duplicate part: ' + key)
            continue
        seen.add(key)
        p = placement['geometry']
        try:
            valid_material(p)
        except ValueError:
            errors.append('Invalid geometry: ' + key)
            continue
        angle, x, y = placement['rotation_deg'], placement['x_mm'], placement['y_mm']
        if angle not in ROTATIONS or not math.isfinite(x) or not math.isfinite(y):
            errors.append('Invalid transform: ' + key)
            continue
        original = affinity.rotate(expected[key], angle, origin=(0, 0))
        minx, miny, _, _ = original.bounds
        reconstructed = affinity.translate(original, x - minx, y - miny)
        if not p.equals(reconstructed):
            errors.append('Part shape differs from declared transform: ' + key)
        if not material.covers(p):
            errors.append('Part outside material: ' + key)
        if p.distance(material.boundary) < clearance:
            errors.append('Material edge clearance: ' + key)
        for other_id, other in placed:
            if p.intersection(other).area > 0:
                errors.append('Overlapping parts: ' + other_id + ', ' + key)
            if p.distance(other) < clearance:
                errors.append('Part clearance: ' + other_id + ', ' + key)
        placed.append((key, p))
    missing = sorted(set(expected) - seen)
    return {'valid': not errors and not missing, 'errors': errors, 'missing_parts': missing}


def nest(material, parts, clearance=0.5, grid=0.5):
    valid_material(material)
    if not math.isfinite(clearance) or clearance < 0 or not math.isfinite(grid) or grid <= 0:
        raise ValueError('Clearance must be nonnegative and grid must be positive')
    if not parts or len(parts) > 50:
        raise ValueError('Provide between 1 and 50 parts')
    for p in parts.values():
        valid_material(p)
        if not isinstance(p, Polygon):
            raise ValueError('Each part must be a single polygon')
    minx, miny, maxx, maxy = material.bounds
    nx, ny = math.floor((maxx-minx)/grid)+1, math.floor((maxy-miny)/grid)+1
    if nx * ny * len(parts) * 4 > MAX_CANDIDATES:
        raise ValueError('Search exceeds candidate budget; increase grid_mm or reduce material/parts')
    placed = []
    # Stable largest-area-first order, then identifier; all ties have fixed order.
    for key in sorted(parts, key=lambda k: (-parts[k].area, k)):
        found = None
        # Keep rotation in its original frame and perform one final translation.
        # Normalizing then translating can round differently from the verifier's
        # declared x/y transform at fractional coordinates (e.g. grid=1.2).
        rotations = [(a, affinity.rotate(parts[key], a, origin=(0, 0))) for a in ROTATIONS]
        for iy in range(ny):
            if found: break
            for ix in range(nx):
                if found: break
                x, y = minx + ix*grid, miny + iy*grid
                for angle, p in rotations:
                    px, py, _, _ = p.bounds
                    candidate = affinity.translate(p, x - px, y - py)
                    if not material.covers(candidate) or candidate.distance(material.boundary) < clearance:
                        continue
                    if any(candidate.intersection(q['geometry']).area > 0 or candidate.distance(q['geometry']) < clearance for q in placed):
                        continue
                    found = dict(id=key, geometry=candidate, rotation_deg=angle, x_mm=x, y_mm=y)
                    break
        if found: placed.append(found)
    check = verify(material, parts, placed, clearance)
    area = sum(p['geometry'].area for p in placed)
    return {'status': 'success' if check['valid'] else 'incomplete',
            'reason': None if check['valid'] else 'Heuristic did not find a complete verified layout; this is not a proof of infeasibility.',
            'clearance_mm': clearance, 'grid_mm': grid,
            'utilization_percent': area/material.area*100, 'material_area_mm2': material.area,
            'placed_area_mm2': area, 'verification': check,
            'material': mapping(material),
            'placements': [{**p, 'geometry': mapping(p['geometry'])} for p in placed]}


def svg_layout(result):
    if result['status'] != 'success' or not result['verification']['valid']:
        raise ValueError('SVG cutting export requires a complete verified layout')
    from .geometry import from_geojson
    material = from_geojson(result['material'])
    minx, miny, maxx, maxy = material.bounds
    def path(g):
        polygons = [g] if g.geom_type == 'Polygon' else g.geoms
        commands = []
        for polygon in polygons:
            for ring in [polygon.exterior, *polygon.interiors]:
                commands.append('M' + ' L'.join(f'{x:.17g},{y:.17g}' for x,y in ring.coords) + ' Z')
        return ' '.join(commands)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{maxx-minx:.17g}mm" height="{maxy-miny:.17g}mm" viewBox="{minx:.17g} {miny:.17g} {maxx-minx:.17g} {maxy-miny:.17g}">',
             '<title>MakeFromThis Stage 02 — verified cutting layout (millimeters)</title>',
             f'<path d="{path(material)}" fill="#eee" fill-rule="evenodd" stroke="black" stroke-width="0.05"/>']
    for p in result['placements']:
        lines.append(f'<path data-part="{escape(p["id"], quote=True)}" d="{path(from_geojson(p["geometry"]))}" fill="none" stroke="blue" stroke-width="0.05"/>')
    return '\n'.join([*lines, '</svg>'])
