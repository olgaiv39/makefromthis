import { useRef, useState } from 'react';
import type { Material, Scene } from '../types';
import { publicGalleryScenes } from '../types';
export default function UploadOrDemo({ scenes, material, onSelect, onBusy }: { scenes: Scene[]; material?: Material; onSelect: (m: Material) => void; onBusy: (busy: boolean) => void }) {
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const revision=useRef(0);
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 8*1024*1024) { setError('Choose an image smaller than 8 MB.'); return; }
    const version=++revision.current;
    setLoading(true);onBusy(true);setError('');
    const url=URL.createObjectURL(file), image=new Image();
    image.onload=()=> { if(version===revision.current) { onSelect({image:url,name:file.name,width:image.naturalWidth,height:image.naturalHeight});setLoading(false);onBusy(false); } else URL.revokeObjectURL(url); };
    image.onerror=()=> { URL.revokeObjectURL(url); if(version===revision.current) {setError('This browser could not open that image. Try a JPEG, PNG or WebP photo.');setLoading(false);onBusy(false);} };
    image.src=url;
  }
  return <section aria-labelledby="material-title"><p className="eyebrow">Add photo</p><h2 id="material-title">Start with your material.</h2><p className="intro">Add a photo, review the detected edge, then enter one measurement.</p>
    <div className="upload-card"><span className="upload-icon" aria-hidden="true">＋</span><h3>Your scraps, your next make</h3><p>Use a photo of one piece you would like to cut.</p><label className="button primary file-label">Add photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{void upload(e.target.files?.[0]);e.target.value='';}} disabled={loading}/></label><small>JPEG, PNG or WebP · up to 8 MB</small></div>
    <ul className="photo-tips"><li>Lay the material flat and photograph it from above.</li><li>Separate overlapping scraps.</li><li>Use a contrasting background.</li><li>Include a ruler, or measure one visible edge.</li></ul><details className="options"><summary>Photo privacy</summary><p className="hint">Finding material sends your photo to this app’s server for image processing. When AI analysis is available and selected, it also sends a smaller copy to Baseten. Cutting checks use the detected edge and your measurements. Photos are not saved by this app.</p></details>
    {loading&&<p role="status">Opening photograph…</p>}{error&&<p role="alert" className="error">{error}</p>}
    {publicGalleryScenes(scenes).length>0&&<><div className="divider">or choose a material to try</div><div className="demo-grid">{publicGalleryScenes(scenes).sort((a,b)=>(a.presentation_order??999)-(b.presentation_order??999)).map(s=><button key={s.id} title={s.description} className={`demo ${material?.image===s.image?'selected':''}`} aria-pressed={material?.image===s.image} onClick={()=>{revision.current++;setLoading(false);onBusy(false);setError('');onSelect({image:s.image,name:s.title||'Reusable material',credit:s.source,width:s.width_px,height:s.height_px});}}><img src={s.thumbnail||s.image} alt="" loading="lazy"/><span>{s.title||'Reusable material'}<small>{s.description||'Find the edge and cut pieces to your own size'}</small></span></button>)}</div></>}
    {material&&<p className="selection" role="status">Selected: {material.name}</p>}
  </section>;
}
