import { useEffect, useRef, useState } from 'react';
import type { Geometry, Material, Point, RectangleDraft } from '../types';
import { rectangleProblem } from '../types';
import { api, serviceMessage } from '../api';
import ErrorMessage from './ErrorMessage';
type State={available:boolean;reason:string|null;provider:string;model_id:string};
type Availability={segmentation:State;recommendation:State};
export function AISegmentation({material,onApply}:{material:Material;onApply:(p:Point[],label:string)=>void}) {
  const [state,setState]=useState<State>(),[busy,setBusy]=useState(false),[error,setError]=useState<Error>();
  const [prediction,setPrediction]=useState<{masks:{geometry:Geometry;confidence:number|null}[];width_px:number;height_px:number}>();
  const abort=useRef<AbortController>();
  useEffect(()=>{const c=new AbortController();void api<Availability>('/api/ai/availability',undefined,c.signal).then(s=>setState(s.segmentation)).catch(()=>{});return()=>{c.abort();abort.current?.abort();};},[]);
  async function detect() {
    const c=new AbortController();abort.current=c;setBusy(true);setError(undefined);setPrediction(undefined);
    try {
      const image=await fetch(material.image,{signal:c.signal}).then(r=>r.blob());
      const response=await fetch('/api/ai/segment',{method:'POST',headers:{'Content-Type':image.type},body:image,signal:c.signal});
      const data=await response.json();
      if(!response.ok)throw Error(typeof data.detail==='string'?serviceMessage(data.detail):'Outline help is unavailable. You can trace the material yourself.');
      if(data.width_px!==material.width||data.height_px!==material.height)throw Error('The suggested outline does not match this photo. Please trace the edge yourself.');
      if(!c.signal.aborted)setPrediction(data);
    }catch(e){if(!c.signal.aborted)setError(e instanceof Error?e:Error('Outline help is unavailable. You can trace the material yourself.'));}
    finally{if(!c.signal.aborted)setBusy(false);}
  }
  // Unconfigured outline inference is not advertised as a working feature.
  if(!state?.available)return null;
  return <details className="options"><summary>Get outline help with AI</summary><p className="hint">This sends your photo for AI processing only when you ask. Review the suggested edge carefully; you will still need to enter a measurement.</p><button disabled={busy} onClick={()=>void detect()}>Suggest an outline</button>{busy&&<><p role="status">Looking for the material edge…</p><button onClick={()=>{abort.current?.abort();setBusy(false);}}>Cancel</button></>}<ErrorMessage error={error}/>{prediction&&<><p role="status">AI-assisted outline. Check it against your material before using it.</p>{prediction.masks.map((m,i)=>{const simple=m.geometry.type==='Polygon'&&m.geometry.coordinates.length===1;return <div key={i}><p>Piece {i+1}</p><button disabled={!simple} onClick={()=>{if(m.geometry.type!=='Polygon')return;const ring=m.geometry.coordinates[0];if(ring.length>101){setError(Error('This edge is too detailed to edit here. Please trace a simpler usable region.'));return;}onApply(ring.slice(0,-1).map(([x,y])=>[x*material.width,y*material.height]),'AI-assisted outline');}}>Use this outline</button>{!simple&&<p className="hint">Please trace one continuous piece without holes for this cutting plan.</p>}</div>;})}</>}</details>;
}
export interface IdeasDraft { materialType:string;preferences:string }
type CuttingOption={project_id:string;width_mm:number;height_mm:number;quantity:number;grid_mm?:number;verified?:boolean;shape_kind?:string;description?:string};
type CuttingAnswer={status:string;reason?:string;project_limitation?:string|null;explanation_source?:string;ranked_projects:{project_id:string;explanation:string}[];options:CuttingOption[]};
export function AIRecommendations({geometry,width,height,clearance,grid,draft,onDraft,pieces,onChoose}:{geometry:Geometry;width:number;height:number;clearance:number;grid:number;draft:IdeasDraft;onDraft:(d:IdeasDraft)=>void;pieces:RectangleDraft;onChoose:(d:RectangleDraft,grid?:number)=>void}) {
  const [state,setState]=useState<State>(),[availabilityError,setAvailabilityError]=useState<Error>();
  const [phase,setPhase]=useState<'idle'|'ai'|'geometry'>('idle'),[error,setError]=useState<Error>();
  const [answer,setAnswer]=useState<CuttingAnswer>();
  const abort=useRef<AbortController>(),availabilityAbort=useRef<AbortController>();
  async function loadAvailability(){
    availabilityAbort.current?.abort();const c=new AbortController();availabilityAbort.current=c;
    setState(undefined);setAvailabilityError(undefined);
    try{
      const result=await api<{material_vision:State;recommendation:State}>('/api/ai/availability',undefined,c.signal);
      if(!c.signal.aborted)setState(result.material_vision.available?result.recommendation:result.material_vision);
    }catch(e){if(!c.signal.aborted)setAvailabilityError(e instanceof Error?e:Error('AI availability could not be checked.'));}
  }
  useEffect(()=>{void loadAvailability();return()=>{availabilityAbort.current?.abort();abort.current?.abort();};},[]);
  const context=JSON.stringify({geometry,clearance,grid,pieces,draft});
  useEffect(()=>{abort.current?.abort();setPhase('idle');setAnswer(undefined);setError(undefined);},[context]);
  const valid=!rectangleProblem(pieces)&&Number.isFinite(clearance)&&clearance>=0&&clearance<=100&&Number.isFinite(grid)&&grid>0;
  async function suggest(useAI:boolean) {
    abort.current?.abort();const c=new AbortController();abort.current=c;setPhase(useAI?'ai':'geometry');setError(undefined);setAnswer(undefined);
    try {
      const result=await api<CuttingAnswer>('/api/ai/cutting-ideas?use_ai='+String(useAI),{material_type:draft.materialType||'unspecified',material_mm:geometry,width_mm:width,height_mm:height,preferences:draft.preferences,clearance_mm:clearance,grid_mm:grid,piece_width_mm:Number(pieces.width),piece_height_mm:Number(pieces.height),quantity:Number(pieces.quantity)},c.signal);
      if(!c.signal.aborted)setAnswer(result);
    }catch(e){if(!c.signal.aborted)setError(e instanceof Error?e:Error('Options could not be checked. Your cutting settings are unchanged.'));}
    finally{if(!c.signal.aborted)setPhase('idle');}
  }
  const options=answer?.status==='live_ai'?answer.ranked_projects.flatMap(p=>{
    const option=answer.options.find(o=>o.project_id===p.project_id);return option?[{...option,explanation:p.explanation}]:[];
  }):answer?.options.map(o=>({...o,explanation:o.description||'This size and quantity passed a complete fit check.'}))??[];
  return <aside className="constraint-panel"><h3>Need a different size?</h3>
    <p className="hint">Find checked square patches, narrow strips and wider rectangular panels. These are cutting blanks, not complete garment patterns. Your measurement and chosen gap are kept.</p>
    <label>Material<input maxLength={120} placeholder="For example, cotton or cardboard" value={draft.materialType} onChange={e=>onDraft({...draft,materialType:e.target.value})}/></label>
    <label>What would you like to make?<input maxLength={1000} value={draft.preferences} onChange={e=>onDraft({...draft,preferences:e.target.value})}/></label>
    <p role="status" className="hint">{availabilityError?'AI availability could not be checked.':!state?'Checking AI availability…':state.available?'Meta AI is ready. Ask for ideas when you’re ready.':'AI ideas are unavailable. Checked options and your own dimensions still work.'}</p>
    <ErrorMessage error={availabilityError}/>{(availabilityError||state&&!state.available)&&<button onClick={()=>void loadAvailability()}>Check AI availability again</button>}
    {state&&!state.available&&<details><summary>AI availability details</summary><p>Reason: {state.reason}</p></details>}
    <button disabled={phase!=='idle'||!valid} onClick={()=>void suggest(false)}>Find fitting options</button>
    {state?.available&&<button disabled={phase!=='idle'||!valid} onClick={()=>void suggest(true)}>Suggest ideas with AI</button>}
    {!valid&&<p className="hint">Enter valid piece dimensions, quantity and gap before finding options.</p>}
    {phase!=='idle'&&<><p role="status">{phase==='ai'?'Checking sizes and asking Meta AI for ideas…':'Checking size and quantity alternatives…'}</p><button onClick={()=>{abort.current?.abort();setPhase('idle');}}>Cancel</button></>}
    <ErrorMessage error={error}/>
    {answer&&<div role="status"><strong>{answer.status==='live_ai'?'Cutting alternatives ranked with Meta AI':options.length?'Fitting options · no AI used':'No verified cutting option found'}</strong>
      {answer.project_limitation&&<p className="selection">{answer.project_limitation}</p>}
      {answer.explanation_source==='supported_operation_descriptions'&&<p className="hint">Meta AI ranked the choices. The descriptions below explain this tool’s supported cutting operations.</p>}
      {!options.length&&<p>The check did not find a practical rectangle or square configuration. Review the measured material size or enter your own smaller dimensions. This is not proof that no arrangement exists.</p>}
      {answer.reason==='ai_disabled'&&<p>AI is disabled on this server. These options were checked without AI.</p>}
      <ul>{options.map(o=><li key={o.project_id}><p>{o.quantity} pieces · {o.width_mm} × {o.height_mm} mm</p><p>{o.explanation}</p><button onClick={()=>onChoose({width:String(o.width_mm),height:String(o.height_mm),quantity:String(o.quantity)},o.grid_mm)}>Use these dimensions</button></li>)}</ul>
      {!!options.length&&<p className="hint">Choose dimensions, then Check how many fit to prepare your pattern.</p>}
    </div>}
    <details><summary>What is shared?</summary><p className="hint">Only your material outline, measurements and preferences are sent for AI ideas when you press Suggest ideas with AI. No photo is sent by this action. Find fitting options uses geometry only.</p></details>
  </aside>;
}
