const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'../src'),cache={};
function load(name) {
 const file=path.resolve(root,name);
 if(cache[file])return cache[file];
 const exports={};cache[file]=exports;
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 new Function('require','exports',code)(id=>id.startsWith('.')?load(path.relative(root,path.resolve(path.dirname(file),id))+(path.extname(id)?'':fs.existsSync(path.resolve(path.dirname(file),id)+'.tsx')?'.tsx':'.ts')):require(id),exports);
 return exports;
}
function render(file,props){return renderToStaticMarkup(React.createElement(load('components/'+file+'.tsx').default,props));}
const h=load('types.ts');
const material={image:'blob:TEST_ONLY',name:'My material',width:400,height:280};
const points=[[40,40],[360,40],[360,240],[40,240]];
const draft={width:'30',height:'20',quantity:'4'};
const request={template_id:'custom-rectangles',scene_scale_mode:'user_calibrated',clearance_mm:.5,grid_mm:2,parts_mm:h.rectangleParts(draft)};
const picker={projects:[],checked:{},selected:'',draft,onDraft:()=>{},clearance:'0.5',onClearance:()=>{},detail:'standard',onDetail:()=>{},busy:false,onCheck:()=>{},onSelect:()=>{},onRetry:()=>{}};

test('rectangle dimensions and quantity become independent closed millimeter polygons',()=>{
 const parts=h.rectangleParts(draft);assert.equal(parts.length,4);
 assert.deepEqual(parts[0],{type:'Polygon',coordinates:[[[0,0],[30,0],[30,20],[0,20],[0,0]]]});
 parts[0].coordinates[0][1][0]=99;assert.equal(parts[1].coordinates[0][1][0],30);
});
test('invalid sizes and fractional or excessive quantities never become requests',()=>{
 for(const change of [{width:''},{width:'Infinity'},{height:'0'},{width:'1001'},{quantity:'0'},{quantity:'2.5'},{quantity:'51'},{quantity:''}])
  assert.throws(()=>h.rectangleParts({...draft,...change}));
});
test('unmeasured and illustrative scales cannot enable a physical pattern',()=>{
 for(const scale of [undefined,0,NaN,Infinity,-1])assert.equal(h.measuredScale(scale,'user_calibrated'),false);
 assert.equal(h.measuredScale(.25,'illustrative'),false);assert.equal(h.measuredScale(.25,'synthetic'),false);
 assert.equal(h.measuredScale(.25,'user_calibrated'),true);
});
test('automatic fitting detail respects existing request work bounds for 1 to 50 rectangles',()=>{
 const g=h.polygon([[10,20],[1010,20],[1010,720],[10,720]],1);
 for(const n of [1,4,25,50])for(const detail of ['quick','standard','closer']) {
  const grid=h.fittingGrid(g,n,detail),cells=(Math.floor(1000/grid)+1)*(Math.floor(700/grid)+1);
  assert.ok(Number.isFinite(grid)&&grid>=.5);
  assert.ok(cells*n*4<=250000);
  assert.ok(cells*n*4*(5+5*n)<=10000000);
 }
});
test('upload-first empty state gives practical guidance without infrastructure copy',()=>{
 const html=render('UploadOrDemo',{scenes:[],onSelect:()=>{},onBusy:()=>{}});
 for(const phrase of ['Add photo','Lay the material flat','Separate overlapping scraps','contrasting background','Include a ruler'])assert.ok(html.includes(phrase));
 assert.doesNotMatch(html,/backend|Stage \d|geometry|regression|dataset|demo-grid/i);
});
test('piece form keeps precision and gap controls in closed More options',()=>{
 const html=render('ProjectPicker',picker);
 for(const phrase of ['Piece width (mm)','Piece height (mm)','Quantity','Check how many fit'])assert.ok(html.includes(phrase));
 assert.match(html,/<details class="options"><summary>More options/);
 assert.doesNotMatch(html,/Search grid|local backend|geometry demonstration/);
 assert.doesNotMatch(html,/miniature|square-tabs|Check sample shapes|2–3 mm/i);
});
test('small tight layouts use a finer bounded grid instead of silently missing clearance positions',()=>{
 assert.equal(h.fittingGrid(h.polygon([[0,0],[40,0],[40,30],[0,30]],1),1),.5);
 assert.throws(()=>h.fittingGrid(h.polygon([[0,0],[40,0],[40,30]],1),0));
});
test('preview requires a calibrated complete checked configuration and preserves its request',()=>{
 const checked={request,layout:{status:'success',placements:[{},{},{},{}],verification:{valid:true,missing_parts:[]}}};
 const before=JSON.stringify(checked.request);
 assert.equal(h.canPreviewPattern(checked,true),true);assert.equal(h.canPreviewPattern(checked,false),false);
 assert.equal(h.canPreviewPattern({...checked,layout:{...checked.layout,status:'incomplete'}},true),false);
 assert.equal(h.canPreviewPattern({...checked,request:{...request,parts_mm:request.parts_mm.slice(1)}},true),false);
 assert.equal(JSON.stringify(checked.request),before);
});
test('material measurements, verified success and technical check failures are visible',()=>{
 const html=render('ProjectPicker',{...picker,materialSize:[160.86,71.06],error:Error('Review the reference length.'),
  checked:{'custom-rectangles':{request,layout:{status:'success',placements:[{},{},{},{}],verification:{valid:true,missing_parts:[]}}}}});
 assert.match(html,/160.9 × 71.1 mm/);assert.match(html,/4 of 4 pieces fit/);assert.match(html,/Continue to your pattern/);
 assert.match(html,/Review the reference length/);
});
test('incomplete heuristic and proven size mismatch have distinct explanations',()=>{
 for(const code of ['heuristic_incomplete','part_exceeds_material_bounds']){
  const html=render('ProjectPicker',{...picker,checked:{'custom-rectangles':{request,layout:{status:'incomplete',placements:[{},{}],
   fit_diagnostics:{code},verification:{valid:false,missing_parts:['part-03','part-04']}}}}});
  assert.match(html,/2 of 4 pieces fit/);assert.match(html,/Find fitting options/);
  assert.match(html,code==='heuristic_incomplete'?/does not prove that none exists/:/larger than the measured material/);
 }
});
test('AI availability is checked explicitly and deterministic alternatives remain available',()=>{
 const html=renderToStaticMarkup(React.createElement(load('components/AIActions.tsx').AIRecommendations,{
  geometry:h.polygon(points,1),width:320,height:200,clearance:.5,grid:4,draft:{materialType:'cotton',preferences:''},onDraft:()=>{},pieces:draft,onChoose:()=>{}}));
 assert.match(html,/Checking AI availability/);assert.match(html,/Find fitting options/);
 assert.match(html,/not complete garment patterns/);
 assert.doesNotMatch(html,/AI ideas are unavailable|2–3 mm|Miniature/);
 const main=fs.readFileSync(path.resolve(root,'main.tsx'),'utf8');assert.doesNotMatch(main,/<AIRecommendations key=/);
 assert.match(main,/grid_mm:chosenGrid/);assert.match(main,/canPreviewPattern\(chosen,calibrated\)/);
});
test('pattern preview centers an unchanged millimeter viewBox and states actual sizes',()=>{
 const g=h.polygon([[15,20],[95.017,20],[95.017,100.578],[15,100.578]],1);
 const layout={status:'success',material:g,material_area_mm2:80.017*80.578,utilization_percent:6.2,
  placements:[{id:'part-01',geometry:h.polygon([[20,25],[30,25],[30,35],[20,35]],1),rotation_deg:0}]};
 const before=JSON.stringify(layout);
 const html=render('LayoutPreview',{material,points,scale:.25,layout,requested:1,pieceDescription:'10 × 10 mm squares',provenance:'Detected outline'});
 assert.match(html,/Pattern size:<\/strong> 80.02 × 80.58 mm/);assert.match(html,/Piece size:<\/strong> 10 × 10 mm/);
 assert.match(html,/preserveAspectRatio="xMidYMid meet"/);assert.match(html,/width="100%" height="100%"/);
 assert.match(html,/Print at 100% size/);assert.match(html,/Physical accuracy depends on your calibration/);
 assert.match(html,/class="pattern-stage"/);assert.equal(JSON.stringify(layout),before);
});
test('ambiguous photographic scene has an actionable refusal instead of a successful mask',()=>{
 const message=load('api.ts').serviceMessage('material_scene_ambiguous');
 assert.match(message,/multiple pieces or objects covering/);assert.match(message,/remove tools and rulers/);
 assert.doesNotMatch(message,/Try tracing|SAM|confidence/);
});

const detection={status:'review_required',width_px:400,height_px:280,
 geometry_px:h.polygon(points,1),requires_confirmation:true,material_type:'unknown',
 provenance:{outline_source:'opencv_pixel_segmentation',ai_image_understanding:false,provider:null,model_id:null,scale_inferred:false}};
test('automatic detection presents a noninteractive preview without manual tracing controls',()=>{
 const html=render('AutomaticOutline',{material,accepted:false,onResult:()=>{},onAccept:()=>{},onReset:()=>{}});
 assert.match(html,/Find material/);assert.match(html,/Photo-only detection is available/);
 assert.doesNotMatch(html,/Manual outline|Finish tracing|Add points|X \(pixels\)|Fine-tune outline|vertex-target|class="interactive"/);
 assert.doesNotMatch(html,/Use this outline/);
});
test('detected boundary requires a separate explicit acceptance before measurements',()=>{
 const html=render('AutomaticOutline',{material,result:detection,accepted:false,onResult:()=>{},onAccept:()=>{},onReset:()=>{}});
 assert.match(html,/Material detected/);assert.match(html,/Review the highlighted area/);
 assert.match(html,/>Use this outline<\/button>/);assert.match(html,/class="outline"/);
 assert.doesNotMatch(html,/SAM prediction|confidence: 1/);
 const accepted=render('AutomaticOutline',{material,result:detection,accepted:true,onResult:()=>{},onAccept:()=>{},onReset:()=>{}});
 assert.match(accepted,/disabled="">Outline accepted/);
});
test('pixel result must align, close and contain a single valid interior contour',()=>{
 assert.deepEqual(h.detectedPoints(detection,material),points);
 for(const change of [{width_px:401},{requires_confirmation:false},{geometry_px:{type:'Polygon',coordinates:[points]}},
  {geometry_px:{type:'Polygon',coordinates:[...detection.geometry_px.coordinates,points]}},
  {geometry_px:h.polygon([[0,0],[400,0],[400,280]],1)},
  {provenance:{...detection.provenance,scale_inferred:true}}])assert.throws(()=>h.detectedPoints({...detection,...change},material));
});
test('normal app imports automatic review and gates continuation on acceptance',()=>{
 const app=fs.readFileSync(path.resolve(root,'main.tsx'),'utf8');
 assert.match(app,/import AutomaticOutline/);assert.doesNotMatch(app,/import MaterialOutlineEditor|Miniature sample|Manual outline/);
 assert.match(app,/accepted&&!outlineProblem\(points\)/);
 assert.match(app,/setDetection\(undefined\);setAccepted\(false\)/);
});
test('photo analysis sends only image bytes to same-origin backend without credentials',async()=>{
 const original=global.fetch;let received;
 global.fetch=async(path,init)=>{received={path,init};return {ok:true,json:async()=>detection};};
 try {
  const blob=new Blob(['TEST_ONLY_IMAGE_BYTES'],{type:'image/jpeg'});
  assert.deepEqual(await load('api.ts').detectMaterial(blob,false),detection);
  assert.equal(received.path,'/api/ai/detect-material?use_ai=false');
  assert.equal(received.init.body,blob);assert.deepEqual(received.init.headers,{'Content-Type':'image/jpeg'});
 }finally{global.fetch=original;}
});
test('uploaded JPEG Blob can be read repeatedly and sent unchanged to offline detection',async()=>{
 // Native Node Blob/fetch exercises the read path; browser CSP is covered by header tests and browser smoke.
 const original=global.fetch,bytes=fs.readFileSync(path.resolve(root,'../../public/ctvg/ctvg-01.jpeg'));
 const image=new Blob([bytes],{type:'image/jpeg'}),url=URL.createObjectURL(image),controller=new AbortController();
 const photoMaterial={...material,image:url};let posts=0;
 global.fetch=async(target,init)=>{
  if(target===url)return original(target,init);
  assert.equal(target,'/api/ai/detect-material?use_ai=false');posts++;
  assert.equal(init.signal,controller.signal);assert.deepEqual(init.headers,{'Content-Type':'image/jpeg'});
  assert.deepEqual(Buffer.from(await init.body.arrayBuffer()),bytes);
  return {ok:true,json:async()=>detection};
 };
 try {
  const read=await load('api.ts').readMaterialPhoto(photoMaterial.image,controller.signal);
  assert.equal(read.type,'image/jpeg');assert.deepEqual(Buffer.from(await read.arrayBuffer()),bytes);
  assert.deepEqual(await load('api.ts').detectMaterial(read,false,controller.signal),detection);
  assert.equal(posts,1);assert.equal(photoMaterial.image,url);
  // Reading again must work: detection does not own or revoke the uploaded URL.
  assert.deepEqual(Buffer.from(await (await load('api.ts').readMaterialPhoto(url)).arrayBuffer()),bytes);
 }finally{global.fetch=original;URL.revokeObjectURL(url);}
});
test('photo-read failure is friendly, does not contact detection and preserves the URL for retry',async()=>{
 const original=global.fetch,url=URL.createObjectURL(new Blob(['TEST_ONLY_BYTES'],{type:'image/jpeg'}));let calls=0;
 global.fetch=async(target)=>{calls++;assert.equal(target,url);throw new TypeError('Failed to fetch');};
 try {
  await assert.rejects(load('api.ts').readMaterialPhoto(url),error=>{
   assert.match(error.message,/couldn’t read your photo/);assert.match(error.message,/Try again/);
   assert.doesNotMatch(error.message,/Failed to fetch/);assert.match(error.details,/before the detection request/);return true;
  });
  assert.equal(calls,1);global.fetch=original;
  assert.equal(await (await load('api.ts').readMaterialPhoto(url)).text(),'TEST_ONLY_BYTES');
 }finally{global.fetch=original;URL.revokeObjectURL(url);}
});
test('failed photo status, unreadable bytes and empty files have photo-specific errors',async()=>{
 const original=global.fetch;
 try {
  for(const response of [{ok:false,status:404},{ok:true,blob:async()=>{throw new TypeError('Failed to fetch');}},
   {ok:true,blob:async()=>new Blob([])}]){
   global.fetch=async()=>response;
   await assert.rejects(load('api.ts').readMaterialPhoto(material.image),error=>{
    assert.match(error.message,/photo/);assert.doesNotMatch(error.message,/Failed to fetch/);
    assert.match(error.details,/Photo read/);
    if(response.status===404)assert.match(error.details,/HTTP 404/);
    return true;
   });
  }
 }finally{global.fetch=original;}
});
test('detection network failures are distinct from local photo-read errors',async()=>{
 const original=global.fetch;global.fetch=async()=>{throw new TypeError('Failed to fetch');};
 try {
  await assert.rejects(load('api.ts').detectMaterial(new Blob(['TEST_ONLY_BYTES']),false),error=>{
   assert.match(error.message,/Couldn’t connect/);assert.doesNotMatch(error.message,/Failed to fetch|read your photo/);
   assert.equal(error.details,'Network request failed');return true;
  });
 }finally{global.fetch=original;}
});
test('unreadable detection response never exposes raw fetch or JSON errors',async()=>{
 const original=global.fetch;
 try {
  for(const error of [new TypeError('Failed to fetch'),new SyntaxError('TEST_ONLY_RAW_JSON_ERROR')]){
   global.fetch=async()=>({ok:true,json:async()=>{throw error;}});
   await assert.rejects(load('api.ts').detectMaterial(new Blob(['TEST_ONLY_BYTES']),false),error=>{
    assert.match(error.message,/detection service/);assert.doesNotMatch(error.message,/Failed to fetch|TEST_ONLY_RAW_JSON_ERROR/);
    assert.equal(error.details,'Invalid or unreadable detection response');return true;
   });
  }
 }finally{global.fetch=original;}
});
test('cancelled photo reads retain abort behavior',async()=>{
 const original=global.fetch,controller=new AbortController();controller.abort();
 const cancelled=new DOMException('Cancelled','AbortError');
 global.fetch=async(url,init)=>{assert.equal(init.signal,controller.signal);throw cancelled;};
 try {await assert.rejects(load('api.ts').readMaterialPhoto(material.image,controller.signal),error=>error===cancelled);}
 finally{global.fetch=original;}
});
test('partial cutting result reports exact placed and missing quantities without an export',()=>{
 const html=render('ProjectPicker',{...picker,checked:{'custom-rectangles':{request,layout:{status:'incomplete',placements:[{},{}],verification:{valid:false,missing_parts:['part-03','part-04']}}}}});
 assert.match(html,/2 of 4 pieces fit/);assert.match(html,/2 pieces could/);assert.match(html,/partial pattern cannot be downloaded/);
 assert.doesNotMatch(html,/Download SVG|verified fit|optimal packing/i);
});
test('cutting download requires actual calibration even if illustrative is marked calibrated',()=>{
 for(const props of [{request},{request,calibrated:false},{request:{...request,scene_scale_mode:'illustrative'},calibrated:true}]) {
  const html=render('ResultsDownload',props);assert.match(html,/real measurement/);assert.doesNotMatch(html,/Prepare pattern|Download SVG/);
 }
 assert.match(render('ResultsDownload',{request,calibrated:true}),/Prepare pattern/);
});
test('measurement panel has no illustrative shortcut or automatic synthetic measurement',()=>{
 const html=render('CalibrationPanel',{material,points,draft:{method:'width',millimeters:'',markers:[]},onDraft:()=>{},onApply:()=>{}});
 assert.match(html,/Known width \(mm\)/);assert.match(html,/Apply measurement/);assert.doesNotMatch(html,/illustrative demo|Known synthetic scale|mm per pixel/);
});
test('unconfigured segmentation is absent instead of a disabled advertised feature',()=>{
 assert.equal(renderToStaticMarkup(React.createElement(load('components/AIActions.tsx').AISegmentation,{material,onApply:()=>{}})),'');
});

test('friendly errors keep exact technical codes in a closed disclosure',()=>{
 const {ServiceError}=load('api.ts');
 const html=render('ErrorMessage',{error:new ServiceError('Please try again shortly.','HTTP 503: geometry_unavailable')});
 assert.match(html,/<p>Please try again shortly/);
 assert.match(html,/<details><summary>Technical details<\/summary><pre>HTTP 503: geometry_unavailable/);
 assert.doesNotMatch(html,/<details open/);
});
test('failed API calls preserve inputs and expose friendly text plus separate diagnostics',async()=>{
 const original=global.fetch;
 global.fetch=async()=>({ok:false,status:503,json:async()=>({detail:'geometry_unavailable'})});
 try {
  await assert.rejects(load('api.ts').api('/api/layouts',{}),error=>{
   assert.match(error.message,/Cutting checks are unavailable/);
   assert.doesNotMatch(error.message,/Shapely|backend|geometry/);
   assert.match(error.details,/HTTP 503: geometry_unavailable/);return true;
  });
 } finally {global.fetch=original;}
});

test('curated card copy shows a natural title and purpose, keeping source credit out of the card',()=>{
 const html=render('UploadOrDemo',{scenes:[{kind:'photograph',annotation_source:'manual_required',
  id:'TEST_ONLY_CARD',title:'Card blanks',description:'Small rectangular blanks for paper crafts',
  source:'TEST_ONLY_SOURCE_CREDIT',image:'/TEST_ONLY_NOT_A_PHOTO_ASSET.jpg',width_px:100,height_px:100,
  mm_per_pixel:null,polygon_px:[],mask:null}],onSelect:()=>{},onBusy:()=>{}});
 assert.match(html,/Card blanks/);assert.match(html,/Small rectangular blanks for paper crafts/);
 assert.doesNotMatch(html,/TEST_ONLY_SOURCE_CREDIT|TEST_ONLY_CARD|Dataset annotation/);
});
