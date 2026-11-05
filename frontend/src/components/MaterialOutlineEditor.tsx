import { useRef, useState } from 'react';
import type { Material, Point } from '../types';
import { outlineProblem, materialGeometry, geometryPath } from '../types';
import { AISegmentation } from './AIActions';
import ImageStage from './ImageStage';
export default function MaterialOutlineEditor({material,points,onChange,provenance,onAIApply}:{material:Material;points:Point[];onChange:(p:Point[])=>void;provenance?:string;onAIApply?:(p:Point[],label:string)=>void}) {
  const [selected,setSelected]=useState(0),[drawing,setDrawing]=useState(true),[mask,setMask]=useState(false);
  const drag=useRef<number|null>(null);
  const manual=!material.scene||!!material.edited,maxCorners=Math.max(100,material.scene?.polygon_px.length||0);
  const active=Math.min(selected,Math.max(0,points.length-1));
  function edit(index:number,p:Point){onChange(points.map((q,i)=>i===index?p:q));}
  return <section aria-labelledby="outline-title"><p className="eyebrow">Trace material</p><h2 id="outline-title">Keep the good parts.</h2><span className="badge">{manual?(provenance||'Manual outline'):'Supplied outline'}</span><p>{manual?'Tap around the usable edge of one flat piece, then finish tracing. Drag a point to adjust it. Leave out holes, frayed edges and damaged areas.':'Review the supplied edge before continuing. You can adjust it by hand.'}</p>
    {material.scene?.annotation_provenance&&<details><summary>Photo credit &amp; outline source</summary><p className="hint">{material.scene.annotation_provenance.authors.join(', ')} · <a href={material.scene.annotation_provenance.url}>Source and license</a>. This supplied outline is not an AI prediction.</p>{!manual&&<button onClick={()=>onChange([...points])}>Adjust outline by hand</button>}</details>}
    {material.credit&&<details><summary>Photo credit</summary><p className="hint">{material.credit}</p></details>}
    {manual&&onAIApply&&<AISegmentation material={material} onApply={onAIApply}/>}
    <ImageStage material={material} interactive={manual} onPoint={p=>{if(drawing&&drag.current===null&&points.length<maxCorners){onChange([...points,p]);setSelected(points.length);}}} onMove={p=>{if(drag.current!==null)edit(drag.current,p);}} onRelease={()=>{drag.current=null;}}>
      {mask&&material.scene?.mask&&<image href={material.scene.mask} width={material.width} height={material.height} opacity=".45"/>}
      {points.length>0&&<path d={geometryPath(materialGeometry(material,points))} className="outline" fillRule="evenodd"/>}
      {manual&&points.map(([x,y],i)=><g key={i} onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId);setSelected(i);drag.current=i;}}><title>Point {i+1}</title><circle cx={x} cy={y} r={Math.max(material.width,material.height)*.013} className="vertex-target"/><circle cx={x} cy={y} r={Math.max(material.width,material.height)*.013} className={`vertex ${active===i?'active':''}`}/></g>)}
    </ImageStage>
    {manual?<><div className="toolbar"><button onClick={()=>setDrawing(!drawing)} aria-pressed={drawing}>{drawing?'Finish tracing':'Add points'}</button><button onClick={()=>onChange(points.slice(0,-1))} disabled={!points.length}>Undo last point</button><button onClick={()=>onChange([])} disabled={!points.length}>Clear outline</button></div><p className="hint">For separate scraps, make a cutting plan for each one.</p>
      <details className="options"><summary>Fine-tune outline</summary><p className="hint">{points.length} of {maxCorners} points used. These positions are in photo pixels, not physical measurements.</p><div className="coordinate-controls"><label>Selected point<select value={active} onChange={e=>setSelected(Number(e.target.value))} disabled={!points.length}>{points.map((_,i)=><option key={i} value={i}>Point {i+1}</option>)}</select></label>{([0,1] as const).map(axis=><label key={axis}>{axis===0?'X':'Y'} (pixels)<input type="number" min="0" max={axis===0?material.width:material.height} step="any" value={points[active]?.[axis]??0} disabled={!points.length} onChange={e=>{const n=e.target.valueAsNumber;if(Number.isFinite(n)){const p=[...points[active]] as Point;p[axis]=Math.max(0,Math.min(axis===0?material.width:material.height,n));edit(active,p);}}}/></label>)}</div><div className="toolbar"><button onClick={()=>{if(points.length<maxCorners){onChange([...points,[material.width/2,material.height/2]]);setSelected(points.length);}}} disabled={points.length>=maxCorners}>Add a point in the middle</button><button onClick={()=>onChange(points.filter((_,i)=>i!==active))} disabled={!points.length}>Delete selected point</button></div></details>
    </>:<label className="check"><input type="checkbox" checked={mask} onChange={e=>setMask(e.target.checked)}/> Show outline overlay</label>}
    {outlineProblem(points)&&<p role="status" className="hint">{outlineProblem(points)}</p>}
  </section>;
}
