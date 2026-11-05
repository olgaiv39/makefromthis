/** Optional REAL browser, existing real photograph, actual offline APIs.
 * Requires AI_ENABLED=false; no paid calls, no masks or annotated outlines loaded.
 * The entered width is a test measurement, not a claim about the source's size.
 */
const {chromium,devices}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function run(){
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 try{
  for(const mobile of [false,true]){
   const context=await browser.newContext({...(mobile?devices['iPhone 13']:{viewport:{width:1280,height:900}}),acceptDownloads:true});
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   const base=process.env.SMOKE_URL||'http://127.0.0.1:8000';
   const availability=await context.request.get(new URL('/api/ai/availability',base).href);
   assert.equal(availability.status(),200);assert.equal((await availability.json()).ai_enabled,false,'Never spend inference credits in this smoke');
   await page.goto(base);
   assert.equal(await page.locator('.demo-grid .demo').count(),0);
   await page.locator('input[type=file]').setInputFiles({name:'textile-photo.jpeg',mimeType:'image/jpeg',buffer:await fs.readFile(path.resolve(__dirname,'../../public/ctvg/ctvg-01.jpeg'))});
   await page.getByText('Selected: textile-photo.jpeg',{exact:true}).waitFor();
   await page.getByRole('button',{name:'Find material',exact:true}).click();
   await page.getByRole('button',{name:'Find material',exact:true}).click();
   await page.getByRole('heading',{name:'Material detected'}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Enter measurements',exact:true}).isEnabled(),false);
   assert.equal(await page.getByText('Manual outline',{exact:true}).count(),0);
   await page.getByRole('button',{name:'Use this outline',exact:true}).click();
   await page.getByRole('button',{name:'Enter measurements',exact:true}).click();
   assert.equal(await page.getByRole('button',{name:'Choose cutting pieces',exact:true}).isEnabled(),false);
   await page.getByLabel('Known width (mm)').fill('120');
   await page.getByRole('button',{name:'Apply measurement'}).click();
   await page.getByRole('button',{name:'Choose cutting pieces',exact:true}).click();
   await page.getByLabel('Piece width (mm)').fill('20');await page.getByLabel('Piece height (mm)').fill('15');
   await page.getByLabel('Quantity',{exact:true}).fill('4');
   assert.equal(await page.getByText('Miniature samples & AI ideas',{exact:true}).count(),0);
   await page.getByRole('button',{name:'Check how many fit',exact:true}).click();
   await page.getByText('4 of 4 pieces fit',{exact:true}).waitFor();
   await page.getByRole('button',{name:'Preview pattern',exact:true}).click();
   assert.equal(await page.locator('[data-part]').count(),4);
   await page.getByLabel('Show my photo',{exact:true}).check();
   const image=await page.locator('.image-stage image').first().getAttribute('href');
   await page.getByRole('button',{name:'← Back',exact:true}).click();
   assert.equal(await page.getByLabel('Quantity',{exact:true}).inputValue(),'4');
   await page.getByRole('button',{name:'Preview pattern',exact:true}).click();
   await page.getByLabel('Show my photo',{exact:true}).check();
   assert.equal(await page.locator('.image-stage image').first().getAttribute('href'),image);
   await page.getByRole('button',{name:'Prepare pattern'}).click();
   const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download SVG',exact:true}).click();
   const file=await download,text=await fs.readFile(await file.path(),'utf8');
   assert.match(text,/<svg/);assert.match(text,/width="[^"]+mm"/);assert.match(text,/height="[^"]+mm"/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const gallery=await context.request.get(new URL('/api/demo-scenes',base).href);assert.deepEqual(await gallery.json(),[]);
   const refused=await context.request.post(new URL('/api/layouts/svg',base).href,{data:{scene_id:'scene-06',template_id:'square-tabs',clearance_mm:.5,grid_mm:.5}});
   assert.equal(refused.status(),422);assert.deepEqual(errors,[]);
   console.log(`${mobile?'Mobile Chromium':'Desktop Chromium'}: real regression photo -> offline contour -> confirmation -> test measurement -> 4 rectangles -> SVG download; no live AI`);
   await context.close();
  }
 }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
