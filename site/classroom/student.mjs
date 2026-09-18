import {api, renderQuestion} from "./shared.mjs";

const params = new URLSearchParams(location.search);
const QUESTIONNAIRE_URL = "./questionnaires/ecg-reference-v0.1.json";
const STORAGE_KEY = "opl-classroom-participant";
const RECORD_URL = "../reference/ecg-id/data/Person_01_rec_1.json";

let questionnaire = null;
let record = null;
let participantId = null;
let participantLabel = "";
let state = null;
let currentTest = null;
let testIndex = 0;
let testResponses = {};
let lastSectionId = null;
let lastLiveQuestionId = null;

const ids=["joinView","classView","joinCode","participantLabel","joinButton","joinStatus","connectionBadge","phaseBadge","sessionTitle","participantDisplay","testView","teachingView","sectionTitle","sectionPrompt","miniTrace","liveQuestionCard","liveQuestion","liveFeedback","doubtForm","doubtText","doubtStatus","closedView"];
const el=Object.fromEntries(ids.map(id=>[id,document.getElementById(id)]));
const ctx=el.miniTrace.getContext("2d");

boot();

async function boot(){
  questionnaire=await fetch(QUESTIONNAIRE_URL).then(r=>r.json());
  record=await fetch(RECORD_URL).then(r=>r.json());
  const code=params.get("room");
  if(code) el.joinCode.value=code;
  restoreParticipant();
  bind();
  if(participantId) {
    el.joinView.hidden=true;
    el.classView.hidden=false;
    await refresh();
  }
  setInterval(refresh,2500);
  setInterval(sendEngagementPing,15000);
}

function bind(){
  el.joinButton.addEventListener("click",join);
  el.doubtForm.addEventListener("submit",async event=>{
    event.preventDefault();
    const text=el.doubtText.value.trim();
    if(!text||!participantId)return;
    await postEvent("doubt_submitted",{text});
    el.doubtText.value="";
    el.doubtStatus.textContent="Sent to teacher.";
    setTimeout(()=>el.doubtStatus.textContent="",1800);
  });
  document.addEventListener("visibilitychange",()=>{
    if(participantId) postEvent("page_visibility_changed",{visible:document.visibilityState==="visible"}).catch(()=>{});
  });
  window.addEventListener("resize",()=>drawMiniTrace());
}

async function join(){
  const code=el.joinCode.value.trim();
  const label=el.participantLabel.value.trim();
  if(!code){el.joinStatus.textContent="Enter the class code.";return;}
  try{
    const result=await api("./api/join",{method:"POST",body:JSON.stringify({join_code:code,label})});
    participantId=result.participant_id;
    participantLabel=result.label||"";
    localStorage.setItem(STORAGE_KEY,JSON.stringify({participantId,participantLabel,joinCode:code}));
    el.joinView.hidden=true;
    el.classView.hidden=false;
    await refresh();
  }catch(error){
    el.joinStatus.textContent=error.message;
  }
}

function restoreParticipant(){
  try{
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY));
    if(saved?.participantId){
      participantId=saved.participantId;
      participantLabel=saved.participantLabel||"";
      if(!el.joinCode.value&&saved.joinCode)el.joinCode.value=saved.joinCode;
    }
  }catch{}
}

async function refresh(){
  if(!participantId)return;
  try{
    const payload=await api("./api/student/state?participant_id="+encodeURIComponent(participantId));
    state=payload.state;
    if(state.questionnaire_definition) questionnaire=state.questionnaire_definition;
    el.connectionBadge.textContent="Connected";
    el.sessionTitle.textContent=state.title||"OPL Classroom";
    el.participantDisplay.textContent=participantLabel||participantId.slice(0,8);
    renderPhase();
  }catch(error){
    el.connectionBadge.textContent="Reconnecting…";
  }
}

function renderPhase(){
  el.phaseBadge.textContent=state.phase;
  el.testView.hidden=true;
  el.teachingView.hidden=true;
  el.closedView.hidden=true;

  if(state.phase==="pre"){
    el.testView.hidden=false;
    ensureTest("pre");
  }else if(state.phase==="teach"){
    el.teachingView.hidden=false;
    renderTeaching();
  }else if(state.phase==="post"){
    el.testView.hidden=false;
    ensureTest("post");
  }else if(state.phase==="closed"){
    el.closedView.hidden=false;
  }else{
    el.testView.hidden=false;
    el.testView.innerHTML='<section class="card"><h2>Waiting for teacher</h2><p class="muted">The class will begin shortly.</p></section>';
  }
}

function ensureTest(phase){
  if(currentTest!==phase){
    currentTest=phase;
    testIndex=0;
    testResponses={};
  }
  renderTestQuestion();
}

function renderTestQuestion(){
  const block=questionnaire[currentTest];
  const items=block.items;
  if(testIndex>=items.length){
    el.testView.innerHTML='<section class="card"><h2>'+block.title+' complete</h2><p class="muted">Waiting for the teacher to continue.</p></section>';
    return;
  }
  const item=items[testIndex];
  el.testView.innerHTML='<section class="card"><div class="muted">'+block.title+' · '+(testIndex+1)+'/'+items.length+'</div><div id="questionHost"></div><div class="row" style="margin-top:10px"><button id="nextTest" class="primary" disabled>'+(testIndex===items.length-1?"Submit":"Next")+'</button></div></section>';
  const host=document.getElementById("questionHost");
  const next=document.getElementById("nextTest");
  renderQuestion(host,item,testResponses[item.id],index=>{
    testResponses[item.id]=index;
    renderQuestion(host,item,index,()=>{},true);
    next.disabled=false;
  });
  next.addEventListener("click",async()=>{
    if(testIndex===items.length-1){
      await postEvent(currentTest==="pre"?"pretest_completed":"posttest_completed",{questionnaire_id:questionnaire.id,responses:testResponses});
      testIndex=items.length;
      renderTestQuestion();
    }else{
      testIndex+=1;
      renderTestQuestion();
    }
  });
}

function renderTeaching(){
  const section=state.section;
  if(section){
    el.sectionTitle.textContent=section.title;
    el.sectionPrompt.textContent=section.prompt;
    if(lastSectionId!==section.id){
      lastSectionId=section.id;
      postEvent("section_viewed",{section_id:section.id}).catch(()=>{});
    }
  }else{
    el.sectionTitle.textContent="Waiting for the next section…";
    el.sectionPrompt.textContent="";
  }
  drawMiniTrace();
  renderLiveQuestion();
}

function renderLiveQuestion(){
  const id=state.live_question_id;
  if(!id){
    el.liveQuestionCard.hidden=true;
    lastLiveQuestionId=null;
    return;
  }
  const question=questionnaire.live.find(q=>q.id===id);
  if(!question)return;
  el.liveQuestionCard.hidden=false;
  if(lastLiveQuestionId!==id){
    lastLiveQuestionId=id;
    el.liveFeedback.textContent="";
    renderQuestion(el.liveQuestion,question,undefined,async index=>{
      renderQuestion(el.liveQuestion,question,index,()=>{},true);
      await postEvent("live_response",{question_id:id,answer:index});
      el.liveFeedback.textContent="Response sent.";
    });
  }
}

function drawMiniTrace(){
  if(!record||!state?.section)return;
  const section=state.section;
  const canvas=el.miniTrace;
  const rect=canvas.getBoundingClientRect();
  const dpr=Math.max(1,window.devicePixelRatio||1);
  canvas.width=Math.max(300,Math.round(rect.width*dpr));
  canvas.height=Math.max(180,Math.round(rect.height*dpr));
  const w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle="#fbfcfd";ctx.fillRect(0,0,w,h);

  const fs=record.sampling_rate_hz;
  const start=Math.max(0,Math.floor((section.window_start_s||0)*fs));
  const len=Math.floor((section.window_length_s||5)*fs);
  const end=Math.min(record.signals.raw.length,start+len);
  const raw=record.signals.raw.slice(start,end);
  const filtered=record.signals.filtered.slice(start,end);
  const mode=section.waveform||"filtered";
  const combined=mode==="overlay"?raw.concat(filtered):mode==="raw"?raw:filtered;
  const min=Math.min(...combined),max=Math.max(...combined);
  const span=Math.max(1,max-min);
  const yMin=min-span*.12,yMax=max+span*.12;

  drawGrid(w,h,section.window_start_s||0,(section.window_start_s||0)+(section.window_length_s||5),dpr);
  if(mode==="raw"||mode==="overlay")drawSignal(record.signals.raw,start,end,yMin,yMax,w,h,"#18384d",1.4*dpr);
  if(mode==="filtered"||mode==="overlay")drawSignal(record.signals.filtered,start,end,yMin,yMax,w,h,"#b65e2e",1.2*dpr);
}

function drawGrid(w,h,startTime,endTime,dpr){
  ctx.lineWidth=.55*dpr;
  for(let t=Math.ceil(startTime/.04)*.04;t<=endTime+.0001;t+=.04){
    const x=(t-startTime)/(endTime-startTime)*w;
    ctx.strokeStyle=Math.round(t*100)%20===0?"#d9e1e7":"#edf1f4";
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  }
  for(let i=1;i<8;i++){
    const y=i/8*h;ctx.strokeStyle="#edf1f4";ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
  }
}

function drawSignal(signal,start,end,yMin,yMax,w,h,color,width){
  ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();
  const n=end-start;
  for(let i=0;i<n;i++){
    const x=n===1?0:i/(n-1)*w;
    const y=h-(signal[start+i]-yMin)/(yMax-yMin)*h;
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  }
  ctx.stroke();
}

async function postEvent(type,payload={}){
  if(!participantId)return;
  await api("./api/event",{method:"POST",body:JSON.stringify({
    participant_id:participantId,
    type,
    client_time:new Date().toISOString(),
    section_id:state?.section?.id||null,
    payload
  })});
}

function sendEngagementPing(){
  if(!participantId||!state)return;
  postEvent("engagement_ping",{
    visible:document.visibilityState==="visible",
    phase:state.phase
  }).catch(()=>{});
}
