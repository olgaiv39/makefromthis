import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import localScenes from '../../backend/app/public-scenes.json';
import { api } from './api';
import type { CheckedProject, FittingDetail, LayoutRequest, Material, MaterialDetection, Point, RectangleDraft, Scene, ScaleMode } from './types';
import { outlineProblem, materialGeometry, geometryBounds, publicGalleryScenes, rectangleParts, rectangleProblem, fittingGrid, measuredScale, detectedPoints, canPreviewPattern } from './types';
import UploadOrDemo from './components/UploadOrDemo';
import AutomaticOutline from './components/AutomaticOutline';
import CalibrationPanel, { type CalibrationDraft } from './components/CalibrationPanel';
import ProjectPicker from './components/ProjectPicker';
import LayoutPreview from './components/LayoutPreview';
import ResultsDownload from './components/ResultsDownload';
import { AIRecommendations, type IdeasDraft } from './components/AIActions';
import './style.css';
const steps=['Add photo','Find material','Enter measurements','Choose cutting pieces','Download pattern'];
function App() {
  const [scaleMode,setScaleMode]=useState<ScaleMode>('user_calibrated');
  const outlineLabel='Detected outline';
  const [detection,setDetection]=useState<MaterialDetection>(),[accepted,setAccepted]=useState(false);
  const [uploadBusy,setUploadBusy]=useState(false);
  const [step,setStep]=useState(0),[material,setMaterial]=useState<Material>(),[points,setPoints]=useState<Point[]>([]),[scale,setScale]=useState<number>();
  const [draft,setDraft]=useState<CalibrationDraft>({method:'width',millimeters:'',markers:[]});
  const [pieces,setPieces]=useState<RectangleDraft>({width:'30',height:'30',quantity:'4'});
  const [ideas,setIdeas]=useState<IdeasDraft>({materialType:'',preferences:''});
  const [gridOverride,setGridOverride]=useState<number>(),[checkError,setCheckError]=useState<Error>();
  const [detail,setDetail]=useState<FittingDetail>('standard');
  const [scenes,setScenes]=useState<Scene[]>(publicGalleryScenes(localScenes as unknown as Scene[]));
  const [checked,setChecked]=useState<Record<string,CheckedProject>>({}),[selected,setSelected]=useState(''),[clearance,setClearance]=useState('0.5'),[busy,setBusy]=useState(false);
  const checkController=useRef<AbortController>();
  const content=useRef<HTMLDivElement>(null);
  useEffect(()=>{const abort=new AbortController();void api<Scene[]>('/api/demo-scenes',undefined,abort.signal).then(data=>setScenes(publicGalleryScenes(data))).catch(()=>{});return()=>{abort.abort();checkController.current?.abort();};},[]);
  useEffect(()=>()=>{if(material?.image.startsWith('blob:'))URL.revokeObjectURL(material.image);},[material?.image]);
  useEffect(()=>{content.current?.focus();},[step]);
  function invalidate(){checkController.current?.abort();setBusy(false);setChecked({});setSelected('');setGridOverride(undefined);setCheckError(undefined);}
  function chooseMaterial(m:Material){invalidate();setDetection(undefined);setAccepted(false);setMaterial({...m,edited:true});setPoints([]);setScale(undefined);setScaleMode('user_calibrated');setDraft({method:'width',millimeters:'',markers:[]});}
  function resetDetection(){invalidate();setDetection(undefined);setAccepted(false);setPoints([]);setScale(undefined);setDraft({method:'width',millimeters:'',markers:[]});}
  function acceptDetection(){if(!detection||!material)return;setPoints(detectedPoints(detection,material));setAccepted(true);setIdeas(d=>({...d,materialType:detection.material_type==='unknown'?'':detection.material_type}));}
  function applyScale(n:number,mode:ScaleMode='user_calibrated'){invalidate();setScale(n);setScaleMode(mode);}
  function chooseCuttingOption(d:RectangleDraft,grid?:number){
    const same=Number(d.width)===Number(pieces.width)&&Number(d.height)===Number(pieces.height)&&Number(d.quantity)===Number(pieces.quantity);
    if(same&&canPreviewPattern(checked[selected],measuredScale(scale,scaleMode))){setPieces(d);return;}
    setPieces(d);invalidate();setGridOverride(grid);
  }
  const calibrated=measuredScale(scale,scaleMode);
  const fullGeometry=useMemo(()=>material&&calibrated?materialGeometry(material,points,scale):undefined,[material,calibrated,points,scale]);
  const bounds=fullGeometry?geometryBounds(fullGeometry):[0,0,0,0];
  let ideaGrid=.5;try{if(fullGeometry)ideaGrid=fittingGrid(fullGeometry,Number(pieces.quantity)||1,detail);}catch{/* The form reports the measurement problem when checked. */}
  async function checkFits(_kind:'rectangles'|'samples') {
    if(!material||!fullGeometry||!calibrated||outlineProblem(points)){setCheckError(Error('Return to measurements and apply a real measurement before checking pieces.'));return;}
    if(!clearance.trim()||!Number.isFinite(Number(clearance))||Number(clearance)<0||Number(clearance)>100){setCheckError(Error('Enter a gap between 0 and 100 mm in More options.'));return;}
    if(rectangleProblem(pieces)){setCheckError(Error(rectangleProblem(pieces)));return;}
    const targets=[{id:'custom-rectangles',parts:rectangleParts(pieces)}];
    let chosenGrid:number;try{chosenGrid=gridOverride??fittingGrid(fullGeometry,Number(pieces.quantity),detail);}catch(e){setCheckError(e instanceof Error?e:Error('Review your measurement.'));return;}
    invalidate();setGridOverride(chosenGrid);const abort=new AbortController();checkController.current=abort;setBusy(true);
    const snapshot:Record<string,CheckedProject>={};
    try {
      for(const project of targets) {
        const request:LayoutRequest={template_id:project.id,material_mm:fullGeometry,scene_scale_mode:'user_calibrated',clearance_mm:Number(clearance),grid_mm:chosenGrid,
          parts_mm:project.parts,
          ...(material.scene?.kind==='photograph'?{source_scene_id:material.scene.id}:{} )};
        try { const layout=await api<NonNullable<CheckedProject['layout']>>('/api/layouts',request,abort.signal);snapshot[project.id]={request,layout}; }
        catch(e){if(abort.signal.aborted)return;snapshot[project.id]={request,error:e instanceof Error?e:Error('The fit could not be checked.')};}
        if(abort.signal.aborted)return;
        setChecked({...snapshot});setSelected(project.id);
      }
    } finally {if(!abort.signal.aborted)setBusy(false);}
  }
  const chosen=checked[selected];
  const complete=canPreviewPattern(chosen,calibrated);
  const requested=chosen?.request.parts_mm?.length??0;
  const pieceDescription=`${pieces.width} × ${pieces.height} mm ${Number(pieces.width)===Number(pieces.height)?'squares':'rectangles'}`;
  const canContinue=step===0?(!!material&&!uploadBusy):step===1?(accepted&&!outlineProblem(points)):step===2?calibrated:step===3?(complete&&calibrated):false;
  function navigate(next:number){checkController.current?.abort();setBusy(false);setStep(next);}
  return <><a className="skip-link" href="#flow">Skip to your cutting plan</a><header className="site-header"><a className="wordmark" href="#" onClick={e=>{e.preventDefault();navigate(0);}}><span className="brand-mark" aria-hidden="true">m.</span>MakeFromThis</a><span className="header-note">A second life for your scraps</span><span className="local-badge">Your cutting table</span></header><main id="flow"><div className="workspace-top"><span className="eyebrow">From leftover to possibility</span><span className="step-count">Step {step+1} of 5</span></div><nav aria-label="Your cutting plan"><ol className="steps">{steps.map((s,i)=><li key={s} className={i===step?'current':i<step?'complete':''}><button aria-current={i===step?'step':undefined} disabled={i>step} onClick={()=>navigate(i)}><span>{i<step?'✓':i+1}</span>{s}</button></li>)}</ol></nav>
    <div ref={content} tabIndex={-1} className="flow-content">
      {step===0&&<UploadOrDemo scenes={scenes} material={material} onSelect={chooseMaterial} onBusy={setUploadBusy}/>}
      {step===1&&material&&<AutomaticOutline key={material.image} material={material} result={detection} accepted={accepted} onResult={setDetection} onAccept={acceptDetection} onReset={resetDetection}/>}
      {step===2&&material&&<CalibrationPanel material={material} points={points} scale={scale} scaleMode={scaleMode} draft={draft} onDraft={d=>{setDraft(d);setScale(undefined);invalidate();}} onApply={applyScale}/>}
      {step===3&&<ProjectPicker projects={[]} checked={checked} selected={selected} draft={pieces} onDraft={d=>{setPieces(d);invalidate();}} clearance={clearance} onClearance={v=>{setClearance(v);invalidate();}} detail={detail} onDetail={v=>{setDetail(v);invalidate();}} busy={busy} onCheck={kind=>void checkFits(kind)} onSelect={setSelected} error={checkError} materialSize={[bounds[2]-bounds[0],bounds[3]-bounds[1]]} onRetry={()=>{}}>
        {fullGeometry&&<AIRecommendations geometry={fullGeometry} width={bounds[2]-bounds[0]} height={bounds[3]-bounds[1]} clearance={Number(clearance)} grid={ideaGrid} draft={ideas} onDraft={setIdeas} pieces={pieces} onChoose={chooseCuttingOption}/>}
      </ProjectPicker>}
      {step===4&&material&&scale&&chosen?.layout&&<><LayoutPreview material={material} points={points} scale={scale} layout={chosen.layout} provenance={outlineLabel} requested={requested} pieceDescription={pieceDescription}/><ResultsDownload key={JSON.stringify(chosen.request)} request={chosen.request} calibrated={calibrated}/></>}
    </div>
    <div className="flow-actions">{step>0&&<button onClick={()=>navigate(step-1)}>← Back</button>}{step<4&&<button className="primary next" disabled={!canContinue||busy} onClick={()=>navigate(step+1)}>{step===0?'Find material':step===1?'Enter measurements':step===2?'Choose cutting pieces':'Preview pattern'} <span aria-hidden="true">→</span></button>}{step===4&&<button className="next" onClick={()=>navigate(0)}>Start another cutting plan</button>}</div>
  </main><footer><span>MakeFromThis · Made for making more from less</span><details><summary>About &amp; privacy</summary><p>Finding material sends your photo to this app’s server. If you choose available AI analysis, a smaller copy is sent to Baseten. Image processing extracts the edge; you confirm it and supply a real measurement. This app does not save photos to an account.</p><p>Check all measurements before cutting. Pieces can turn in quarter turns. Consider fabric grain, print direction, seam allowance and blade width yourself.</p><p>Built for the Meta Global AI Developer Hackathon.</p></details></footer></>;
}
createRoot(document.getElementById('root')!).render(<App/>);
