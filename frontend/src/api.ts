export function serviceMessage(detail: string): string {
  const messages: Record<string,string> = {
    request_too_large: 'This file is too large. Try a smaller photo.',
    image_or_request_too_large: 'Choose a JPEG, PNG or WebP photo under 8 MB.',
    image_too_large: 'Choose a photo under 8 MB.',
    unsupported_image_type: 'Use a JPEG, PNG or WebP photograph.',
    invalid_image: 'This photo could not be opened. Try a JPEG, PNG or WebP photograph.',
    invalid_image_dimensions: 'Use a photo at least 48 pixels across and no more than 16 megapixels.',
    image_processing_unavailable: 'Automatic detection is unavailable here. Your photo is still here.',
    detection_busy: 'Another photo is being processed. Please try again shortly.',
    foreground_not_clear: 'We couldn’t separate the material from the background. Try a contrasting background and even light.',
    background_too_complex: 'The background is too busy. Place one flat piece on a plain contrasting surface.',
    multiple_material_pieces: 'We found more than one piece. Photograph one separate piece at a time.',
    material_scene_ambiguous: 'We found multiple pieces or objects covering the material. Try a photo of one flat piece with its full edge visible, and remove tools and rulers.',
    foreground_fills_frame: 'Leave some clear background around every edge of the material.',
    material_edge_missing: 'The whole edge needs to be visible. Leave clear space around the material.',
    internal_holes_unsupported: 'This piece has an internal cut-out we can’t handle automatically yet. Try a piece without holes.',
    photo_not_suitable: 'The material may be folded, overlapped or partly hidden. Photograph one flat, fully visible piece.',
    invalid_material_guidance: 'The photo analysis could not be used. Try again or use photo-only detection.',
    guidance_region_incomplete: 'The photo analysis did not locate the whole piece. Try photo-only detection or a clearer photo.',
    invalid_detected_geometry: 'We couldn’t find a complete usable edge. Try a clearer photo.',
    contour_too_complex: 'This edge is too detailed to use reliably. Try a simpler piece.',
    geometry_service_busy: 'Another cutting check is running. Please try again shortly.',
    request_budget_exhausted: 'Please wait a minute before trying again.',
    request_body_timeout: 'The upload took too long. Check your connection or choose a smaller photo.',
    inference_busy: 'AI is busy. Try again later or continue without it.',
    provider_timeout: 'AI took too long to answer. You can try again or continue without it.',
    provider_authentication_failed: 'AI suggestions are unavailable right now. You can still check your cutting pieces.',
    provider_unavailable: 'AI could not answer right now. Your cutting settings are unchanged. Try Find fitting options without AI.',
    provider_refused: 'AI could not provide ideas for this request. You can still find fitting options without AI.',
    ai_disabled: 'AI is not available here. Photo-only detection is still available.',
    credentials_missing: 'AI is not available here. Photo-only detection is still available.',
    geometry_unavailable: 'Cutting checks are unavailable right now. Your photo and measurements are still here.',
    malformed_provider_output: 'AI returned an answer we couldn’t use. Your cutting settings have not changed.',
    incomplete_provider_output: 'The AI answer was cut short. Your cutting settings have not changed.',
    invalid_recommendation_output: 'The AI answer did not contain fitting cutting pieces. Your size and quantity are unchanged.',
    dimensions_must_match_calibrated_geometry: 'Please reapply your measurement before checking the fit.',
  };
  if (messages[detail])return messages[detail];
  if (/budget|candidate|work estimate/i.test(detail))return 'This check is too large. Try fewer pieces or Quicker in More options.';
  return 'We couldn’t complete this check. Review your outline and measurements, then try again.';
}
export class ServiceError extends Error {
  constructor(message: string, public details: string) { super(message);this.name='ServiceError'; }
}
export async function readMaterialPhoto(url:string,signal?:AbortSignal):Promise<Blob> {
  try {
    const response=await fetch(url,{signal});
    if(!response.ok)throw new ServiceError('We couldn’t read your photo. Try again, or add the photo again.',`Photo read failed: HTTP ${response.status}`);
    const photo=await response.blob();
    if(!photo.size)throw new ServiceError('This photo appears to be empty. Please add it again.','Photo read returned no image bytes');
    return photo;
  }catch(error) {
    if(error instanceof Error&&error.name==='AbortError')throw error;
    if(error instanceof ServiceError)throw error;
    throw new ServiceError('We couldn’t read your photo. Try again, or add the photo again.','Photo read failed before the detection request');
  }
}
async function failed(response: Response): Promise<ServiceError> {
  let detail='';
  try {
    const raw=(await response.json()).detail;
    detail=typeof raw==='string'?raw:Array.isArray(raw)?raw.map(x=>x.msg).join('; '):typeof raw?.reason==='string'?raw.reason:'';
  }catch { /* A non-JSON server response still gets a useful message. */ }
  return new ServiceError(detail?serviceMessage(detail):'The cutting service could not answer. Please try again.',`HTTP ${response.status}${detail?': '+detail.slice(0,4000):''}`);
}
async function request(path: string, init: RequestInit): Promise<Response> {
  try{return await fetch(path,init);}
  catch(error) {
    if(error instanceof Error && error.name==='AbortError')throw error;
    throw new ServiceError('Couldn’t connect. Check your connection and try again. Your inputs are still here.','Network request failed');
  }
}
export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response=await request(path,{signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  if(!response.ok)throw await failed(response);
  if(!(response.headers.get('content-type')||'').includes('json'))throw new ServiceError('The cutting service could not answer. Please try again.','Expected JSON response');
  return response.json();
}
export async function exportSvg(body: unknown, signal?: AbortSignal): Promise<Blob> {
  const response=await request('/api/layouts/svg',{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!response.ok)throw await failed(response);
  const text=await response.text(),xml=new DOMParser().parseFromString(text,'image/svg+xml'),svg=xml.documentElement;
  if(xml.querySelector('parsererror')||svg.localName!=='svg'||!svg.getAttribute('width')?.endsWith('mm')||!svg.getAttribute('height')?.endsWith('mm'))
    throw new ServiceError('The pattern file could not be prepared. Please try again.','Invalid SVG or missing millimeter dimensions');
  return new Blob([text],{type:'image/svg+xml'});
}
export async function detectMaterial(image:Blob,useAI:boolean,signal?:AbortSignal):Promise<import('./types').MaterialDetection> {
  const response=await request('/api/ai/detect-material?use_ai='+String(useAI),{method:'POST',signal,headers:{'Content-Type':image.type},body:image});
  if(!response.ok)throw await failed(response);
  try{return await response.json();}
  catch(error) {
    if(error instanceof Error&&error.name==='AbortError')throw error;
    throw new ServiceError('The detection service couldn’t finish its response. Please try again.','Invalid or unreadable detection response');
  }
}
