/* OPL Experimental Physiology v0.1 — browser-only single-channel viewer.
   All loaded samples remain local; baseline and inversion are rendering state only. */
'use strict';
const $ = id => document.getElementById(id);
const canvas = $('plot'), ctx=canvas.getContext('2d');
const state={samples:[],originalName:'',yUnit:'arbitrary normalized units',kind:'SYNTHETIC',
             base:null,cursors:[],nextCursor:0,dragging:false,invert:false};
let catalog=[];
function escaped(s){return String(s??'unknown').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
function sourceLabel(s){return `${s.title} [${s.signal_class}]`}
async function init(){
  try{
    const r=await fetch('../data/sources.json'); if(!r.ok)throw new Error('HTTP '+r.status);
    catalog=(await r.json()).sources; const sel=$('source');sel.innerHTML='';
    for(const s of catalog){let o=document.createElement('option');o.value=s.id;o.textContent=sourceLabel(s);sel.appendChild(o)}
    sel.addEventListener('change',showSource);showSource();
  }catch(err){$('source').innerHTML='<option>Catalogue unavailable</option>'; $('source-status').textContent=`Could not load source catalogue: ${err.message}. Run via python -m http.server 8000.`}
  await loadDemo();
}
function showSource(){
  const s=catalog.find(x=>x.id===$('source').value);if(!s)return;
  $('source-status').textContent=s.access_status.replaceAll('-',' · ');
  $('source-information').innerHTML=`<div><b>Species:</b> ${escaped(s.species)}</div><div><b>Preparation:</b> ${escaped(s.preparation)}</div><div><b>Evidence:</b> ${escaped(s.signal_class)}</div><div><b>Licence:</b> ${escaped(s.licence)}</div><div><b>Review:</b> ${escaped(s.reuse_review)}</div><div><b>Calibration:</b> ${escaped(s.known_calibration)}</div><div><b>Limits:</b> ${escaped(s.caveats)}</div>`;
  $('source-link').href=s.source_url; $('show-historic').disabled=!s.image_url;
}
function parseCSV(input){
  const lines=input.trim().split(/\r?\n/);
  if(lines.length<3)throw new Error('CSV must contain a header and at least two samples');
  const cols=lines[0].replace(/^\uFEFF/,'').split(',').map(x=>x.trim());
  const ix=cols.indexOf('time_ms'),iy=cols.indexOf('value');
  if(ix<0||iy<0)throw new Error('Expected exact columns: time_ms,value');
  const result=[];let previous=-Infinity;
  if(lines.length>500002)throw new Error('Large file: maximum 500,000 rows in v0.1');
  for(let i=1;i<lines.length;i++){
    if(!lines[i].trim())continue;
    const cs=lines[i].split(',');
    if(cs.length<cols.length)throw new Error('Missing column at row '+(i+1));
    const t=Number(cs[ix]),v=Number(cs[iy]);
    if(cs[ix].trim()===''||cs[iy].trim()===''||!Number.isFinite(t)||!Number.isFinite(v))throw new Error('Invalid numeric value at row '+(i+1));
    if(t<=previous)throw new Error('time_ms must be strictly increasing (row '+(i+1)+')');
    result.push({t,v});previous=t;
  }
  if(result.length<2)throw new Error('At least two nonblank samples required');
  return result;
}
function loadWaveform(samples,{kind,name,unit}){
 state.samples=samples;state.kind=kind;state.originalName=name;state.yUnit=unit;
 state.base=null;state.cursors=[];state.nextCursor=0;state.invert=false;$('invert').checked=false;
 $('trace-name').textContent=`${name} · ${samples.length} samples`;
 const lab=$('truth-label');lab.textContent=kind==='SYNTHETIC'?'SYNTHETIC DEMONSTRATION — NOT BIOLOGICAL DATA':'USER-IMPORTED CSV — PROVENANCE NOT VERIFIED';
 $('historic').hidden=true;$('digital').hidden=false; $('hint').textContent=kind==='SYNTHETIC'?'Practice cursors and baseline on a mathematical demo; not experimental data.':'Imported data remain local. Confirm this file’s units and provenance before interpretation.';
 draw();updateMetrics();
}
async function loadDemo(){
 try{const r=await fetch('../examples/demo_SYNTHETIC_muscle_twitch.csv');if(!r.ok)throw new Error('HTTP '+r.status);
 loadWaveform(parseCSV(await r.text()),{kind:'SYNTHETIC',name:'Synthetic twitch (interaction test)',unit:'arbitrary normalized units'});
 }catch(err){$('hint').textContent='Demo could not load: '+err.message;}
}
$('demo').addEventListener('click',loadDemo);
$('show-historic').addEventListener('click',()=>{
 const s=catalog.find(x=>x.id===$('source').value);if(!s?.image_url)return;
 $('historic').hidden=false;$('digital').hidden=true;
 $('historic-image').src=s.image_url;
 $('historic-image').style.width='100%';
 $('historic-credit').textContent=s.image_label+' Attribution: '+s.attribution+' Source licence: '+s.licence;
 $('truth-label').textContent='REAL HISTORICAL IMAGE — PHYSICAL CALIBRATION UNVERIFIED';
 $('trace-name').textContent=s.title;
});
$('image-zoom').addEventListener('input',e=>{$('historic-image').style.width=e.target.value+'%'});

$('file').addEventListener('change',async e=>{
  const f=e.target.files?.[0];if(!f)return;
  try{loadWaveform(parseCSV(await f.text()),{kind:'UNVERIFIED',name:f.name,unit:'unspecified (CSV value)'})}
  catch(err){window.alert('CSV import error: '+err.message)}
});
$('invert').addEventListener('change',e=>{state.invert=e.target.checked;draw();updateMetrics()});
$('clear').addEventListener('click',()=>{state.cursors=[];state.nextCursor=0;draw();updateMetrics()});
$('reset').addEventListener('click',()=>{state.cursors=[];state.nextCursor=0;state.base=null;state.invert=false;$('invert').checked=false;draw();updateMetrics()});
function dims(){
 const rect=canvas.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2);
 if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){
  canvas.width=Math.max(200,Math.round(rect.width*dpr));canvas.height=Math.max(200,Math.round(rect.height*dpr));
 }
 ctx.setTransform(dpr,0,0,dpr,0,0);
 return {w:rect.width,h:rect.height,l:58,r:20,t:24,b:54};
}
function range(){const s=state.samples;if(!s.length)return {xmin:0,xmax:1,ymin:0,ymax:1};
 let mn=Infinity,mx=-Infinity;for(const point of s){mn=Math.min(mn,point.v);mx=Math.max(mx,point.v)}const pad=Math.max((mx-mn)*.15,0.05);
 return {xmin:s[0].t,xmax:s[s.length-1].t,ymin:mn-pad,ymax:mx+pad};
}
function coords(){const d=dims(),r=range();const pw=d.w-d.l-d.r,ph=d.h-d.t-d.b;
 const x=t=>d.l+(t-r.xmin)/(r.xmax-r.xmin)*pw;
 const y=v=>d.t+(state.invert?(v-r.ymin):(r.ymax-v))/(r.ymax-r.ymin)*ph;
 const tOf=xpix=>r.xmin+Math.max(0,Math.min(1,(xpix-d.l)/pw))*(r.xmax-r.xmin);
 const vOf=ypix=>state.invert?(r.ymin+(ypix-d.t)/ph*(r.ymax-r.ymin)):(r.ymax-(ypix-d.t)/ph*(r.ymax-r.ymin));
 return {d,r,x,y,tOf,vOf};
}
function nearest(t){const s=state.samples;let l=0,h=s.length-1;while(l<h){const m=(l+h)>>1;if(s[m].t<t)l=m+1;else h=m}if(l>0&&Math.abs(s[l-1].t-t)<Math.abs(s[l].t-t))l--;return s[l]}
function draw(){
 const {d,r,x,y}=coords();ctx.clearRect(0,0,d.w,d.h);
 ctx.fillStyle='#ffffff';ctx.fillRect(0,0,d.w,d.h);ctx.font='12px system-ui';
 const xmin=r.xmin,xmax=r.xmax;ctx.strokeStyle='#e6ecf2';ctx.lineWidth=1;
 for(let i=0;i<=5;i++){let px=d.l+(d.w-d.l-d.r)*i/5;ctx.beginPath();ctx.moveTo(px,d.t);ctx.lineTo(px,d.h-d.b);ctx.stroke();ctx.fillStyle='#516276';ctx.fillText((xmin+(xmax-xmin)*i/5).toFixed(0),px-12,d.h-28)}
 for(let i=0;i<=4;i++){let yy=d.t+(d.h-d.t-d.b)*i/4;ctx.beginPath();ctx.moveTo(d.l,yy);ctx.lineTo(d.w-d.r,yy);ctx.stroke();ctx.fillStyle='#516276';let vv=state.invert?r.ymin+(r.ymax-r.ymin)*i/4:r.ymax-(r.ymax-r.ymin)*i/4;ctx.fillText(vv.toFixed(2),3,yy+4)}
 ctx.fillStyle='#314458';ctx.fillText('Time (ms)',(d.w+d.l-d.r)/2-26,d.h-7);ctx.fillText('Value ('+state.yUnit+')',d.l+6,14);
 const base=state.base??((r.ymin+r.ymax)/2);ctx.setLineDash([7,5]);ctx.strokeStyle='#a76b26';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(d.l,y(base));ctx.lineTo(d.w-d.r,y(base));ctx.stroke();ctx.setLineDash([]);
 const s=state.samples;if(s.length){ctx.strokeStyle='#096d9e';ctx.lineWidth=1.5;ctx.beginPath();
 // Preserve impulse maxima/minima in dense recordings: draw a vertical min-max envelope per display pixel.
 const maxPixels=Math.max(1,Math.floor(d.w-d.l-d.r));
 if(s.length>maxPixels*3){let previousPixel=-1,lo=Infinity,hi=-Infinity;
  const flush=()=>{if(previousPixel<0)return;const px=d.l+previousPixel+.5;ctx.moveTo(px,y(lo));ctx.lineTo(px,y(hi));};
  for(const q of s){const pixel=Math.min(maxPixels-1,Math.floor((q.t-r.xmin)/(r.xmax-r.xmin)*maxPixels));
   if(pixel!==previousPixel){flush();previousPixel=pixel;lo=q.v;hi=q.v}else{lo=Math.min(lo,q.v);hi=Math.max(hi,q.v)}}flush();
 }else{ctx.moveTo(x(s[0].t),y(s[0].v));for(let i=1;i<s.length;i++)ctx.lineTo(x(s[i].t),y(s[i].v));}
 ctx.stroke()}
 const cols=['#a2395b','#16835a'];for(let i=0;i<state.cursors.length;i++){const point=state.cursors[i],xx=x(point.t);ctx.strokeStyle=cols[i];ctx.lineWidth=1.7;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xx,d.t);ctx.lineTo(xx,d.h-d.b);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=cols[i];ctx.fillText(i?'B':'A',xx+5,d.t+14);ctx.beginPath();ctx.arc(xx,y(point.v),4,0,Math.PI*2);ctx.fill()}
}
function updateMetrics(){let base=state.base;
 $('baseline').textContent=base===null?'midline (display)':'at '+base.toFixed(3)+' '+state.yUnit;
 if(state.cursors.length<2){$('dt').textContent='—';$('dy').textContent='—';return}
 const [a,b]=state.cursors;$('dt').textContent=Math.abs(b.t-a.t).toFixed(2)+' ms';
 $('dy').textContent=Math.abs(b.v-a.v).toFixed(4)+' '+state.yUnit;
}
function point(e){const b=canvas.getBoundingClientRect();return{x:e.clientX-b.left,y:e.clientY-b.top}}
canvas.addEventListener('pointerdown',e=>{
 if(!state.samples.length)return;
 const p=point(e),c=coords(),baselineY=c.y(state.base??((c.r.ymin+c.r.ymax)/2));
 if(Math.abs(p.y-baselineY)<=11&&p.x>=c.d.l){state.dragging=true;canvas.setPointerCapture(e.pointerId);return}
 if(p.x<c.d.l||p.x>c.d.w-c.d.r||p.y<c.d.t||p.y>c.d.h-c.d.b)return;
 const sample=nearest(c.tOf(p.x));state.cursors[state.nextCursor]=sample;state.nextCursor=(state.nextCursor+1)%2;draw();updateMetrics();
});
canvas.addEventListener('pointermove',e=>{if(!state.dragging)return;const p=point(e),c=coords();state.base=Math.max(c.r.ymin,Math.min(c.r.ymax,c.vOf(p.y)));draw();updateMetrics()});
canvas.addEventListener('pointerup',()=>{state.dragging=false});canvas.addEventListener('pointercancel',()=>{state.dragging=false});
window.addEventListener('resize',draw);
init();
