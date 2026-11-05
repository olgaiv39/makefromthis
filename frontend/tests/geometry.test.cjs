const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
// Exercise the actual shared frontend helpers with the existing TS compiler.
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/types.ts'),'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const helpers = {};
new Function('exports',compiled)(helpers);
const { polygon, geometryPath, outlineProblem } = helpers;
test('manual calibration scales and closes the outline',()=>{
 assert.deepEqual(polygon([[10,20],[30,20],[30,40]],.25),{type:'Polygon',coordinates:[[[2.5,5],[7.5,5],[7.5,10],[2.5,5]]]});
});
test('layout overlay converts mm back to source pixels',()=>{
 assert.equal(geometryPath({type:'Polygon',coordinates:[[[1,2],[3,2],[1,2]]]},.25),'M4,8 L12,8 L4,8 Z');
});
test('holes and disconnected layout regions remain separate SVG subpaths',()=>{
 const p={type:'MultiPolygon',coordinates:[[[[0,0],[1,0],[0,0]],[[.2,.2],[.3,.2],[.2,.2]]],[[[3,0],[4,0],[3,0]]]]};
 assert.equal((geometryPath(p).match(/M/g)||[]).length,3);
});
test('too few corners and zero area are blocked',()=>{
 assert.ok(outlineProblem([[0,0],[1,1]]));
 assert.ok(outlineProblem([[0,0],[1,1],[2,2]]));
});
test('crossing outline with nonzero signed area is blocked',()=>{
 assert.match(outlineProblem([[0,0],[4,3],[0,3],[3,0]]),/cross/);
});
test('duplicate corners and non-finite inputs are blocked',()=>{
 assert.ok(outlineProblem([[0,0],[4,0],[4,0],[0,3]]));
 assert.ok(outlineProblem([[0,0],[Infinity,0],[0,3]]));
});
test('valid concave outline remains usable',()=>{
 assert.equal(outlineProblem([[0,0],[4,0],[4,1],[1,1],[1,4],[0,4]]),undefined);
});

test('scene material geometry preserves holes through mm calibration',()=>{
 const scene={geometry_px:{type:'Polygon',coordinates:[[[0,0],[100,0],[100,100],[0,100],[0,0]],[[20,20],[40,20],[40,40],[20,40],[20,20]]]}};
 const g=helpers.materialGeometry({scene},[],.04);
 assert.equal(g.coordinates.length,2);
 assert.deepEqual(g.coordinates[1][1],[1.6,.8]);
 assert.deepEqual(helpers.geometryBounds(g),[0,0,4,4]);
});
test('disconnected material bounds and calibration include every piece',()=>{
 const g={type:'MultiPolygon',coordinates:[[[[10,10],[30,10],[10,30],[10,10]]],[[[80,10],[100,10],[80,30],[80,10]]]]};
 const actual=helpers.materialGeometry({scene:{geometry_px:g}},[[10,10],[30,10],[10,30]],.1);
 assert.equal(actual.type,'MultiPolygon');
 assert.deepEqual(helpers.geometryBounds(actual),[1,1,10,3]);
 assert.equal((geometryPath(actual).match(/M/g)||[]).length,2);
});
test('uploaded manual outlines keep their existing single-ring behavior',()=>{
 const p=[[10,10],[30,10],[10,30]];
 assert.deepEqual(helpers.materialGeometry({},p,.25),polygon(p,.25));
});

test('manual edits of dataset annotations use edited geometry rather than original labels',()=>{
 const original={type:'Polygon',coordinates:[[[0,0],[100,0],[0,100],[0,0]]]};
 const edited=[[10,10],[20,10],[10,20]];
 assert.deepEqual(helpers.materialGeometry({edited:true,scene:{geometry_px:original}},edited,.1),polygon(edited,.1));
});

test('public gallery excludes synthetic, legacy and explicitly hidden fixtures',()=>{
 const photo={kind:'photograph',id:'TEST_ONLY_CONTRACT_RECORD',annotation_source:'manual_required'};
 assert.deepEqual(helpers.publicGalleryScenes([photo,{kind:'synthetic',id:'scene-01'},
  {id:'legacy'}, {...photo,id:'hidden-photo',gallery_visible:false}]),[photo]);
});

test('unavailable originals leave an empty offline fallback without benchmark substitutions',()=>{
 const fallback=require('../../backend/app/public-scenes.json');
 assert.equal(fallback.length,0);
 assert.deepEqual(helpers.publicGalleryScenes(fallback),fallback);
 const entry=fs.readFileSync(path.join(__dirname,'../src/main.tsx'),'utf8');
 assert.match(entry,/import localScenes from '\.\.\/\.\.\/backend\/app\/public-scenes\.json'/);
 assert.doesNotMatch(entry,/import localScenes from '\.\.\/\.\.\/backend\/app\/(?:ctvg-)?scenes\.json'/);
 const component=fs.readFileSync(path.join(__dirname,'../src/components/UploadOrDemo.tsx'),'utf8');
 assert.match(component,/publicGalleryScenes\(scenes\)/);
 assert.doesNotMatch(component,/Sample |synthetic samples|synthetic demo/);
});

test('actual upload component hides all annotated benchmark and synthetic fixtures',()=>{
 const React=require('react');
 const {renderToStaticMarkup}=require('react-dom/server');
 const source=fs.readFileSync(path.join(__dirname,'../src/components/UploadOrDemo.tsx'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const component={};
 new Function('require','exports',code)(name=>name==='../types'?helpers:require(name),component);
 const fixtures=require('../../backend/app/scenes.json');
 const html=renderToStaticMarkup(React.createElement(component.default,{
  scenes:fixtures,onSelect:()=>{},onBusy:()=>{},
 }));
 assert.equal((html.match(/class="demo /g)||[]).length,0);
 assert.match(html,/Add photo/);
 assert.doesNotMatch(html,/or choose a real material photograph/);
 for(const fixture of fixtures) {
  assert.ok(!html.includes(fixture.title));
  assert.ok(!html.includes(fixture.image));
 }
 assert.doesNotMatch(html,/Sample \d|Regression sample|synthetic demo/);
});
