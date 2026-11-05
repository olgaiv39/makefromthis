import type { ReactNode } from 'react';
import type { CheckedProject, FittingDetail, Project, RectangleDraft } from '../types';
import { rectangleProblem } from '../types';
import ErrorMessage from './ErrorMessage';
export default function ProjectPicker({checked,draft,onDraft,clearance,onClearance,detail,onDetail,busy,onCheck,children,error,materialSize}: {
  projects:Project[];checked:Record<string,CheckedProject>;selected:string;draft:RectangleDraft;onDraft:(d:RectangleDraft)=>void;
  clearance:string;onClearance:(s:string)=>void;detail:FittingDetail;onDetail:(s:FittingDetail)=>void;busy:boolean;
  materialSize?:[number,number];onCheck:(kind:'rectangles'|'samples')=>void;onSelect:(id:string)=>void;error:Error|undefined;onRetry:()=>void;children?:ReactNode;
}) {
  const result=checked['custom-rectangles'],problem=rectangleProblem(draft);
  const validGap=clearance.trim()!==''&&Number.isFinite(Number(clearance))&&Number(clearance)>=0&&Number(clearance)<=100;
  const placed=result?.layout?.placements.length??0,missing=result?.layout?.verification.missing_parts.length??0;
  return <section aria-labelledby="projects-title"><p className="eyebrow">Choose cutting pieces</p><h2 id="projects-title">What size do you need?</h2><p>Cut squares or rectangles for patchwork, paper crafts, labels and more. Enter the finished cutting size, including any seam allowance you need.</p>
    {materialSize&&<p className="selection">At your measurement, the material spans {materialSize[0].toFixed(1)} × {materialSize[1].toFixed(1)} mm. If this looks wrong, go Back and check the reference length in millimeters.</p>}
    <div className="coordinate-controls"><label>Piece width (mm)<input type="number" inputMode="decimal" min="0.1" max="1000" step="any" value={draft.width} onChange={e=>onDraft({...draft,width:e.target.value})}/></label><label>Piece height (mm)<input type="number" inputMode="decimal" min="0.1" max="1000" step="any" value={draft.height} onChange={e=>onDraft({...draft,height:e.target.value})}/></label><label>Quantity<input type="number" inputMode="numeric" min="1" max="50" step="1" value={draft.quantity} onChange={e=>onDraft({...draft,quantity:e.target.value})}/></label></div>
    <p className="hint">For squares, use the same width and height. 10 mm = 1 cm.</p>
    <details className="options"><summary>More options</summary><div className="coordinate-controls"><label>Gap around pieces (mm)<input type="number" inputMode="decimal" min="0" max="100" step="any" value={clearance} onChange={e=>onClearance(e.target.value)}/></label><label>Fitting detail<select value={detail} onChange={e=>onDetail(e.target.value as FittingDetail)}><option value="standard">Standard</option><option value="closer">Try more positions</option><option value="quick">Quicker</option></select></label></div><p className="hint">The gap is kept between pieces and away from the detected edge. It does not add seam allowance. Pieces may turn a quarter turn; check fabric grain or print direction before cutting.</p></details>
    {!validGap&&<p role="status" className="hint">Enter a gap between 0 and 100 mm in More options.</p>}{problem&&<p role="status" className="hint">{problem}</p>}
    <button className="primary" disabled={busy||!!problem||!validGap} onClick={()=>onCheck('rectangles')}>{busy?'Finding room for your pieces…':'Check how many fit'}</button>
    {busy&&<p role="status">Trying an arrangement on your material…</p>}
    <ErrorMessage error={error||result?.error}/>
    {result?.layout&&<div className="selection" role="status"><strong>{placed} of {result.request.parts_mm?.length} pieces fit</strong><p>{draft.width} × {draft.height} mm each.</p>{result.layout.status==='success'&&result.layout.verification.valid?<p>All pieces are inside your outline with the chosen gap. Continue to your pattern.</p>:<><p>{missing} {missing===1?'piece could':'pieces could'} not be placed in this check. Try fewer or smaller pieces, or try more positions in More options.</p><p>A different arrangement may fit more. A partial pattern cannot be downloaded. Use Find fitting options below for checked size and quantity alternatives.</p></>}</div>}
    {result?.layout?.fit_diagnostics&&<><p className="hint">{result.layout.fit_diagnostics.code==='part_exceeds_material_bounds'?'At least one requested piece is larger than the measured material allows, including the gap.':result.layout.fit_diagnostics.code==='requested_area_exceeds_material_area'?'The requested pieces need more area than the measured material provides. Reduce the quantity or size.':result.layout.fit_diagnostics.code==='heuristic_incomplete'?'The search did not find a complete arrangement. This does not prove that none exists.':''}</p><details><summary>Cutting check details</summary><p className="hint">Result: {result.layout.fit_diagnostics.code} · Gap: {result.request.clearance_mm} mm · Position step: {result.request.grid_mm} mm</p></details></>}
    {children}
  </section>;
}
