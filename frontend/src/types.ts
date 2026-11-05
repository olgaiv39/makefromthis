export type Point = [number, number];
export type Geometry = { type: 'Polygon'; coordinates: Point[][] } | { type: 'MultiPolygon'; coordinates: Point[][][] };
export type ScaleMode = 'synthetic' | 'user_calibrated' | 'illustrative';
export interface Scene { gallery_visible?: boolean; kind?: string; annotation_source?: string; scale_status?: string; thumbnail?: string | null; illustrative_mm_per_pixel?: number | null; annotation_provenance?: { authors: string[]; doi: string; license: string; url: string; source_image: string; source_annotation: string; annotation_url: string }; title?: string; description?: string; featured?: boolean; presentation_order?: number; expected_fit?: string; geometry_px?: Geometry; id: string; source: string; image: string; mask: string | null; width_px: number; height_px: number; mm_per_pixel: number | null; polygon_px: number[][] }
export interface Material { edited?: boolean; credit?: string; image: string; name: string; width: number; height: number; scene?: Scene }
export interface MaterialDetection {
  status:'review_required';width_px:number;height_px:number;geometry_px:Geometry;
  material_type:string;requires_confirmation:true;
  provenance:{outline_source:'opencv_pixel_segmentation';ai_image_understanding:boolean;provider:string|null;model_id:string|null;scale_inferred:false};
}
export function detectedPoints(result:MaterialDetection,material:Material):Point[] {
  if(result.status!=='review_required'||result.requires_confirmation!==true||result.width_px!==material.width||result.height_px!==material.height
    ||result.geometry_px.type!=='Polygon'||result.geometry_px.coordinates.length!==1
    ||result.provenance.outline_source!=='opencv_pixel_segmentation'||result.provenance.scale_inferred!==false)
    throw Error('The detected outline does not match this photo. Try another photograph.');
  const ring=result.geometry_px.coordinates[0];
  if(ring.length<4||ring.length>101||ring[0][0]!==ring[ring.length-1]?.[0]||ring[0][1]!==ring[ring.length-1]?.[1]
    ||ring.some(([x,y])=>!Number.isFinite(x)||!Number.isFinite(y)||x<=0||y<=0||x>=material.width||y>=material.height))
    throw Error('The material edge could not be found reliably. Try another photograph.');
  const points=ring.slice(0,-1);if(outlineProblem(points))throw Error('The detected edge could not be used. Try another photograph.');
  return points;
}
// Both fetched data and offline fallback pass through this boundary. Older APIs
// may still return synthetic fixtures; those must never become gallery choices.
export function publicGalleryScenes(scenes: Scene[]): Scene[] {
  return scenes.filter(s=>s.kind==='photograph' && s.annotation_source==='manual_required'
    && s.gallery_visible!==false && !s.mask && !s.geometry_px && !s.polygon_px?.length
    && !s.annotation_provenance && s.mm_per_pixel==null);
}
export interface Project { id: string; name: string; description: string; parts: Geometry[]; units: string }
export interface LayoutRequest { parts_mm?: Geometry[]; source_scene_id?: string; scene_mm_per_pixel?: number; scene_scale_mode?: ScaleMode; scene_id?: string; template_id: string; clearance_mm: number; grid_mm: number; material_mm?: Geometry }
export interface Layout { fit_diagnostics?:{code:string;width_mm:number;height_mm:number;requested_area_mm2:number;requested_count:number;placed_count:number;grid_mm:number;clearance_mm:number};scale_status?: ScaleMode; scale_note?: string; status: 'success' | 'incomplete'; reason: string | null; material_area_mm2: number; utilization_percent: number; placed_area_mm2: number; material: Geometry; verification: { valid: boolean; errors: string[]; missing_parts: string[] }; placements: { id: string; geometry: Geometry; rotation_deg: number; x_mm: number; y_mm: number }[] }
export interface CheckedProject { request: LayoutRequest; layout?: Layout; error?: Error }
export interface RectangleDraft { width: string; height: string; quantity: string }
export type FittingDetail = 'standard' | 'closer' | 'quick';
export function rectangleProblem(draft: RectangleDraft): string | undefined {
  if (![draft.width,draft.height].every(s=>s.trim()!=='' && Number.isFinite(Number(s)) && Number(s)>=.1 && Number(s)<=1000))
    return 'Enter a width and height between 0.1 and 1,000 mm.';
  const n=Number(draft.quantity);
  if (!draft.quantity.trim() || !Number.isInteger(n) || n<1 || n>50) return 'Choose a whole number of pieces from 1 to 50.';
}
export function rectangleParts(draft: RectangleDraft): Geometry[] {
  const problem=rectangleProblem(draft);if(problem)throw Error(problem);
  const w=Number(draft.width),h=Number(draft.height);
  return Array.from({length:Number(draft.quantity)},()=>polygon([[0,0],[w,0],[w,h],[0,h]],1));
}
// Choose a bounded position step for existing API limits; no packing algorithm here.
export function fittingGrid(g: Geometry, count: number, detail: FittingDetail='standard'): number {
  const [x,y,a,b]=geometryBounds(g),vertices=rings(g).reduce((n,r)=>n+r.length,0);
  if(!Number.isInteger(count)||count<1||count>50||!Number.isFinite(a-x)||a<=x||b<=y)throw Error('Check your measurements and piece quantity.');
  const cells=Math.min(250000/(4*count),10000000/(4*count*(vertices+5*count)));
  const allowed=(step:number)=>(Math.floor((a-x)/step)+1)*(Math.floor((b-y)/step)+1)<=cells;
  let step=Math.max(.5,Math.floor(Math.max(a-x,b-y)/(detail==='closer'?120:detail==='quick'?30:80)*10)/10);
  if(!allowed(step)) {
    let low=step,high=Math.max(step,a-x,b-y);
    for(let i=0;i<40;i++){const mid=(low+high)/2;if(allowed(mid))high=mid;else low=mid;}
    step=high;
  }
  step=Math.ceil(step*10)/10;
  if(step>100)throw Error('This measurement and quantity exceed the cutting check limit. Review your measurement or choose fewer pieces.');
  return step;
}
export function canPreviewPattern(checked:CheckedProject|undefined,calibrated:boolean):boolean {
  const layout=checked?.layout;
  return !!(calibrated&&checked?.request.scene_scale_mode==='user_calibrated'&&layout?.status==='success'&&layout.verification.valid&&layout.verification.missing_parts.length===0
    &&layout.placements.length===checked?.request.parts_mm?.length);
}
export function measuredScale(scale: number | undefined, mode: ScaleMode): boolean {
  return mode==='user_calibrated' && scale!==undefined && Number.isFinite(scale) && scale>0;
}
export function rings(g: Geometry): Point[][] { return g.type === 'Polygon' ? g.coordinates : g.coordinates.flat(); }
export function geometryPath(g: Geometry, scale = 1): string { return rings(g).map(r => 'M' + r.map(([x,y]) => `${x / scale},${y / scale}`).join(' L') + ' Z').join(' '); }
export function polygon(points: Point[], scale: number): Geometry { return { type: 'Polygon', coordinates: [[...points, points[0]].map(([x,y]) => [x * scale, y * scale])] }; }
export function outlineProblem(points: Point[]): string | undefined {
  if (points.length < 3) return 'Add at least three corners to close your outline.';
  if (points.some(p => p.some(v => !Number.isFinite(v)))) return 'Coordinates must be finite numbers.';
  const area = Math.abs(points.reduce((s,[x,y],i) => { const [a,b] = points[(i+1)%points.length]; return s + x*b - a*y; },0))/2;
  if (area < 0.01) return 'The outline must enclose an area.';
  const cross = (a: Point,b: Point,c: Point) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const on = (a: Point,b: Point,c: Point) => Math.abs(cross(a,b,c))<1e-8 && c[0]>=Math.min(a[0],b[0]) && c[0]<=Math.max(a[0],b[0]) && c[1]>=Math.min(a[1],b[1]) && c[1]<=Math.max(a[1],b[1]);
  for(let i=0;i<points.length;i++) {
    const a=points[i],b=points[(i+1)%points.length];
    if(Math.hypot(a[0]-b[0],a[1]-b[1])<.01) return 'Remove duplicate neighboring corners.';
    for(let j=i+1;j<points.length;j++) {
      if(j===i+1 || (i===0&&j===points.length-1))continue;
      const c=points[j],d=points[(j+1)%points.length];
      if((cross(a,b,c)*cross(a,b,d)<0 && cross(c,d,a)*cross(c,d,b)<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b)) return 'Outline edges cross or touch. Move or remove a corner.';
    }
  }
  // The backend still performs the authoritative validity and containment checks.
  return undefined;
}

// New scenes carry full topology; legacy single-ring scenes remain supported.
export function materialGeometry(material: Material, points: Point[], scale = 1): Geometry {
  const g=material.edited?undefined:material.scene?.geometry_px;
  if(!g)return polygon(points,scale);
  const ring=(r:Point[]):Point[]=>r.map(([x,y])=>[x*scale,y*scale]);
  return g.type==='Polygon'?{type:'Polygon',coordinates:g.coordinates.map(ring)}:
    {type:'MultiPolygon',coordinates:g.coordinates.map(p=>p.map(ring))};
}
export function geometryBounds(g: Geometry): [number,number,number,number] {
  const points=rings(g).flat(),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  return [Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
}
