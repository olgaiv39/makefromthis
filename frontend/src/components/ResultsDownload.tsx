import { useEffect, useRef, useState } from 'react';
import { exportSvg } from '../api';
import type { LayoutRequest } from '../types';
import ErrorMessage from './ErrorMessage';
export default function ResultsDownload({request,calibrated=false}:{request:LayoutRequest;calibrated?:boolean}) {
  const [loading,setLoading]=useState(false),[error,setError]=useState<Error>(),[url,setUrl]=useState('');
  const controller=useRef<AbortController>();
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>()=>{if(url)URL.revokeObjectURL(url);},[url]);
  const measured=calibrated&&request.scene_scale_mode!=='illustrative';
  async function prepare() {
    if(!measured)return;
    controller.current?.abort();const abort=new AbortController();controller.current=abort;
    setLoading(true);setError(undefined);
    try{const blob=await exportSvg(request,abort.signal);if(!abort.signal.aborted)setUrl(URL.createObjectURL(blob));}
    catch(e){if(!abort.signal.aborted)setError(e instanceof Error?e:Error('The pattern could not be prepared. Please try again.'));}
    finally{if(!abort.signal.aborted)setLoading(false);}
  }
  return <section className="download-panel" aria-labelledby="download-title"><h3 id="download-title">Download your pattern</h3>{!measured?<p role="alert">Go back and apply a real measurement before downloading a cutting file.</p>:<><p>SVG cutting file · millimeters. Print or import at 100% size and check a known measurement before cutting.</p>{url?<a className="button primary" href={url} download="makefromthis-cutting-pattern.svg">Download SVG</a>:<button className="primary" disabled={loading} onClick={()=>void prepare()}>{loading?'Preparing your pattern…':'Prepare pattern'}</button>}{loading&&<p role="status">Checking the pieces and preparing your file…</p>}{url&&<p role="status" className="fit">Your pattern is ready to save.</p>}</>}<ErrorMessage error={error}/></section>;
}
