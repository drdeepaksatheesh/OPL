/* Synchronized original squid giant axon two-channel training view.
 * No invented units, artificial filtering, current baseline correction, or data uploads.
 */
'use strict';
const $=id=>document.getElementById(id);
const rec={time:[],vm:[],stim:[],cursors:[],turn:0,window:[992,1030],ready:false,source:'a1t18'};
function fail(reason){rec.ready=false;rec.time=[];rec.vm=[];rec.stim=[];rec.cursors=[];for(const id of ['full','focus','mark','clear'])$(id).disabled=true;for(const id of ['vm','stim']){const cv=$(id);cv.getContext('2d').clearRect(0,0,cv.width,cv.height)}$('integrity').className='fail';$('integrity').textContent='Integrity/load failure: '+reason;}
function decodeCSV(raw){
 const rows=raw.trim().split(/\r?\n/);if(rows[0]!=='time_ms,value')throw Error('Unexpected CSV header');
 const t=[],v=[]; let prev=-Infinity;
 for(let j=1;j<rows.length;j++){
  const p=rows[j].split(',');if(p.length!==2||!p[0].trim()||!p[1].trim())throw Error('Invalid row '+j);
  const a=Number(p[0]),b=Number(p[1]);if(!Number.isFinite(a)||!Number.isFinite(b)||a<=prev)throw Error('Invalid time/value at '+j);
  t.push(a);v.push(b);prev=a;
 }return {t,v};
}
async function verified(channel,meta){
 const r=await fetch('../examples/real/'+meta.file);if(!r.ok)throw Error('Missing '+channel);
 const bytes=await r.arrayBuffer();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
 if(hash!==meta.sha256)throw Error(channel+' SHA-256 mismatch');
 const result=decodeCSV(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
 if(result.t.length!==meta.sample_count)throw Error(channel+' sample count mismatch');return result;
}
async function init(){try{
 if(!globalThis.crypto?.subtle)throw Error('HTTPS or localhost required for SHA-256 verification');
 const resp=await fetch('../examples/real/sgamp_a1t18_excerpt_manifest.json');if(!resp.ok)throw Error('Missing provenance manifest');
 const m=await resp.json();
 if(m.data_class!=='VERIFIED_EXCERPT_FROM_AUTHENTIC_ORIGINAL'||m.record_id!=='a1t18'||m.source_doi!=='10.13026/C25C73'||m.source_sampling_frequency_hz!==125000)throw Error('Provenance mismatch');
 const [v,s]=await Promise.all([verified('Vm',m.channels.Vmembrane),verified('current',m.channels.Istim)]);
 if(v.t.length!==s.t.length||v.t.length!==4751)throw Error('Channel-length mismatch');
 for(let i=0;i<v.t.length;i++){if(v.t[i]!==s.t[i]||Math.abs(v.t[i]-(992+i*.008))>1e-6)throw Error('Channel desynchronization at sample '+i)}
 rec.time=v.t;rec.vm=v.v;rec.stim=s.v;rec.ready=true;
 $('integrity').className='pass';$('integrity').textContent='✓ Both channels verified (SHA-256), 4,751 aligned samples per channel, 0.008 ms sampling interval.';
 for(const id of ['full','focus','mark','clear'])$(id).disabled=false;
 draw();
 }catch(e){fail(e.message)}}
function domain(a){const b=rec.time;const left=Math.max(0,b.findIndex(t=>t>=a[0]));let right=b.findIndex(t=>t>a[1]);if(right<0)right=b.length;
 return [left,right]}
function plot(canvas,values,unit){
 const rect=canvas.getBoundingClientRect();if(rect.width<20||rect.height<30)return;
 const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
 const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);const w=rect.width,h=rect.height,L=65,R=17,T=16,B=37;
 const [i0,i1]=domain(rec.window);if(i1-i0<2)return;
 const yvals=values.slice(i0,i1),ymin0=Math.min(...yvals),ymax0=Math.max(...yvals),pad=Math.max((ymax0-ymin0)*.12,.01),ymin=ymin0-pad,ymax=ymax0+pad;
 const x=t=>L+(t-rec.window[0])/(rec.window[1]-rec.window[0])*(w-L-R),y=v=>T+(ymax-v)/(ymax-ymin)*(h-T-B);
 c.fillStyle='#fff';c.fillRect(0,0,w,h);c.font='12px system-ui';c.strokeStyle='#e2eaf1';c.lineWidth=1;
 for(let k=0;k<=4;k++){let p=L+(w-L-R)*k/4;c.beginPath();c.moveTo(p,T);c.lineTo(p,h-B);c.stroke();c.fillStyle='#516780';c.fillText((rec.window[0]+(rec.window[1]-rec.window[0])*k/4).toFixed(rec.window[1]-rec.window[0]>8?1:2),Math.min(w-R-42,Math.max(L-12,p-16)),h-18)}
 for(let k=0;k<=4;k++){const yy=T+(h-T-B)*k/4;c.beginPath();c.moveTo(L,yy);c.lineTo(w-R,yy);c.stroke();c.fillStyle='#516780';c.fillText((ymax-(ymax-ymin)*k/4).toFixed(1),7,yy+4)}
 c.strokeStyle=unit==='mV'?'#086c9d':'#98622b';c.lineWidth=1.45;c.beginPath();c.moveTo(x(rec.time[i0]),y(values[i0]));for(let j=i0+1;j<i1;j++)c.lineTo(x(rec.time[j]),y(values[j]));c.stroke();
 rec.cursors.forEach((t,k)=>{if(t<rec.window[0]||t>rec.window[1])return;c.strokeStyle=k?'#a82f59':'#208055';c.lineWidth=1.6;c.setLineDash([5,3]);c.beginPath();c.moveTo(x(t),T);c.lineTo(x(t),h-B);c.stroke();c.setLineDash([]);c.fillStyle=c.strokeStyle;c.fillText(k?'B':'A',x(t)+3,T+11)});
 c.fillStyle='#294457';c.fillText('Time (ms)',w/2-27,h-3);c.fillText(unit,L+6,13);
}
function draw(){if(!rec.ready)return;plot($('vm'),rec.vm,'mV');plot($('stim'),rec.stim,'µA/cm²');update()}
function update(){const [a,b]=rec.cursors;$('a').textContent=a===undefined?'—':a.toFixed(3)+' ms';$('b').textContent=b===undefined?'—':b.toFixed(3)+' ms';$('delta').textContent=(a===undefined||b===undefined)?'—':(b-a).toFixed(3)+' ms';
 if(a===undefined||b===undefined)return;
 function at(time,values){let j=Math.round((time-992)/.008);return values[Math.max(0,Math.min(values.length-1,j))]}
 $('readout').textContent='A: Vm '+at(a,rec.vm).toFixed(2)+' mV; stimulus '+at(a,rec.stim).toFixed(3)+' µA/cm². B: Vm '+at(b,rec.vm).toFixed(2)+' mV; stimulus '+at(b,rec.stim).toFixed(3)+' µA/cm². Cursors are nearest recorded sample.';
}
function choose(e){if(!rec.ready)return;const r=e.currentTarget.getBoundingClientRect(),x=e.clientX-r.left,L=65,R=17;if(x<L||x>r.width-R)return;
 const t=rec.window[0]+((x-L)/(r.width-L-R))*(rec.window[1]-rec.window[0]);
 const idx=Math.max(0,Math.min(rec.time.length-1,Math.round((t-992)/.008)));
 rec.cursors[rec.turn]=rec.time[idx];rec.turn=(rec.turn+1)%2;draw();
}
for(const id of ['vm','stim'])$(id).addEventListener('pointerdown',choose);
$('full').addEventListener('click',()=>{rec.window=[992,1030];draw()});
$('focus').addEventListener('click',()=>{rec.window=[999,1004];draw()});
$('clear').addEventListener('click',()=>{rec.cursors=[];rec.turn=0;$('readout').textContent='Tap either waveform to set A and B.';draw()});
$('mark').addEventListener('click',()=>{
 // Explicit teaching algorithm, NOT author's event labels: stimulus >1 µA/cm², then first Vm positive maximum in [1000,1002]ms.
 const onset=rec.time.findIndex((t,i)=>t>=999&&t<=1002&&rec.stim[i]>1);
 if(onset<0){fail('No current-pulse onset detected');return}
 let max=-Infinity,peak=-1;for(let i=onset;i<rec.time.length&&rec.time[i]<=1002;i++){if(rec.vm[i]>max){max=rec.vm[i];peak=i}}
 if(peak<0){fail('First positive peak not found');return}
 rec.window=[999,1004];rec.cursors=[rec.time[onset],rec.time[peak]];rec.turn=0;draw();
 $('readout').textContent+=' Automatic markers: stimulus first >1 µA/cm² and maximum Vm through 1002 ms (detector-defined). Not spike initiation.';
});
window.addEventListener('resize',()=>{if(rec.ready)draw()});init();
