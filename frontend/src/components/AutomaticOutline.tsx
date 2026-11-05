import { useEffect, useRef, useState } from 'react';
import type { Material, MaterialDetection } from '../types';
import { detectedPoints, geometryPath } from '../types';
import { api, detectMaterial, readMaterialPhoto } from '../api';
import ImageStage from './ImageStage';
import ErrorMessage from './ErrorMessage';

export default function AutomaticOutline({material,result,accepted,onResult,onAccept,onReset}:{
 material:Material;result?:MaterialDetection;accepted:boolean;
 onResult:(d:MaterialDetection)=>void;onAccept:()=>void;onReset:()=>void;
}) {
 const [available,setAvailable]=useState(false),[offline,setOffline]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<Error>();
 const abort=useRef<AbortController>();
 useEffect(()=>{const c=new AbortController();void api<{material_vision:{available:boolean}}>('/api/ai/availability',undefined,c.signal)
  .then(r=>setAvailable(r.material_vision.available)).catch(()=>{});return()=>{c.abort();abort.current?.abort();};},[]);
 async function detect() {
  abort.current?.abort();const c=new AbortController();abort.current=c;
  onReset();setBusy(true);setError(undefined);
  try {
   const photo=await readMaterialPhoto(material.image,c.signal);
   const found=await detectMaterial(photo,available&&!offline,c.signal);
   detectedPoints(found,material);
   if(!c.signal.aborted)onResult(found);
  }catch(e){if(!c.signal.aborted)setError(e instanceof Error?e:Error('This photo could not be processed. Try another photograph.'));}
  finally{if(!c.signal.aborted)setBusy(false);}
 }
 return <section aria-labelledby="outline-title"><p className="eyebrow">Find material</p><h2 id="outline-title">{busy?'Finding your material…':result?'Material detected':'Let’s find the edge.'}</h2>
  <p>{result?'Review the highlighted area. Check that it follows every edge before accepting.':'Use one flat, fully visible piece on a contrasting background. No drawing needed.'}</p>
  <ImageStage material={material}>{result&&<path d={geometryPath(result.geometry_px)} className="outline" fillRule="evenodd"/>}</ImageStage>
  {available?<><p className="hint">Meta AI can help locate your material. Finding the edge sends your photo for analysis once when you press the button.</p><label><input type="checkbox" checked={offline} onChange={e=>setOffline(e.target.checked)} disabled={busy}/> Use photo-only detection</label></>:<p className="hint">Photo-only detection is available. AI photo analysis is unavailable here.</p>}
  <div className="editor-actions"><button disabled={busy} onClick={()=>void detect()}>{result||error?'Try again':'Find material'}</button>
   {busy&&<button onClick={()=>{abort.current?.abort();setBusy(false);}}>Cancel</button>}
   {result&&<button className="primary" disabled={accepted||busy} onClick={onAccept}>{accepted?'Outline accepted':'Use this outline'}</button>}</div>
  {busy&&<p role="status">Finding your material…</p>}{accepted&&<p role="status">Outline accepted. Enter a measurement to continue.</p>}
  <ErrorMessage error={error}/><p className="hint">If the edge is wrong, take another photo with flatter material, more space around it and a simpler background.</p>
  {result&&<details><summary>How this outline was made</summary><p>{result.provenance.ai_image_understanding?'Meta AI assessed the photo and suggested an approximate region. ':''}Image processing extracted this boundary from pixels. It is approximate, not a SAM mask or a physical measurement. Check it carefully.</p></details>}
  {material.credit&&<details><summary>Photo credit</summary><p>{material.credit}</p></details>}
 </section>;
}
