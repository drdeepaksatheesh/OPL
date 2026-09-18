import {api, downloadJson, escapeHtml} from "./shared.mjs";

const params = new URLSearchParams(location.search);
const teacherToken = params.get("teacher") || "";
const authHeaders = teacherToken ? {"X-OPL-Teacher-Token":teacherToken} : {};
const QUESTIONNAIRE_URL = "./questionnaires/ecg-reference-v0.1.json";

const sections = [
  {
    id:"raw-filtered",
    title:"Raw and filtered ECG",
    prompt:"Compare the original digital recording with the source-provided filtered channel. What visibly changes and what should remain traceable?",
    window_start_s:0,
    window_length_s:5,
    waveform:"overlay"
  },
  {
    id:"baseline",
    title:"Choose a baseline",
    prompt:"Use an isoelectric reference and think of vertical deflection as distance from that baseline.",
    window_start_s:5,
    window_length_s:5,
    waveform:"filtered"
  },
  {
    id:"measurement",
    title:"Measure ECG geometry",
    prompt:"Place two sample-anchored markers. Horizontal distance becomes time; vertical distance is reported relative to the selected baseline.",
    window_start_s:10,
    window_length_s:5,
    waveform:"filtered"
  }
];

let questionnaire = null;
let state = null;
let events = [];

const ids = ["joinCode","studentUrl","joinedCount","preCount","activeCount","postCount","phaseStatus","sectionList","liveQuestion","liveResponses","doubtList","prePostSummary","engagementSummary","copyStudentUrl","exportSession","openLiveQuestion","closeLiveQuestion","connectionBadge","questionnaireFile","questionnaireStatus"];
const el = Object.fromEntries(ids.map(id=>[id,document.getElementById(id)]));

boot();

async function boot(){
  questionnaire = await fetch(QUESTIONNAIRE_URL).then(r=>r.json());
  renderSections();
  bind();
  await refresh();
  setInterval(refresh, 2500);
}

function bind(){
  document.querySelectorAll("[data-phase]").forEach(button=>{
    button.addEventListener("click",()=>teacherAction({type:"set_phase",phase:button.dataset.phase}));
  });
  el.copyStudentUrl.addEventListener("click",async()=>{
    const url = state?.student_url || "";
    if (!url) return;
    await navigator.clipboard.writeText(url).catch(()=>{});
    el.copyStudentUrl.textContent="Copied";
    setTimeout(()=>el.copyStudentUrl.textContent="Copy student link",1200);
  });
  el.exportSession.addEventListener("click",async()=>{
    const data = await api("./api/export",{headers:authHeaders});
    downloadJson("OPL_classroom_"+(data.session_id||"session")+".json",data);
  });
  el.openLiveQuestion.addEventListener("click",()=>{
    const q=questionnaire.live[0];
    teacherAction({type:"open_live_question",question_id:q.id});
  });
  el.closeLiveQuestion.addEventListener("click",()=>teacherAction({type:"close_live_question"}));
  window.addEventListener("message", event=>{
    if(event.origin!==location.origin) return;
    if(event.data?.type!=="opl-reference-view" || !event.data.view) return;
    teacherAction({type:"set_reference_view",reference_view:event.data.view}).catch(()=>{});
  });

  el.questionnaireFile.addEventListener("change", async event=>{
    const file=event.target.files?.[0];
    if(!file)return;
    try{
      const definition=JSON.parse(await file.text());
      validateQuestionnaire(definition);
      await teacherAction({type:"set_questionnaire",questionnaire:definition});
      el.questionnaireStatus.textContent="Loaded: "+definition.title+" · "+(definition.version||"unversioned");
    }catch(error){
      el.questionnaireStatus.textContent="Could not load questionnaire: "+error.message;
    }finally{
      event.target.value="";
    }
  });
}

function renderSections(){
  el.sectionList.innerHTML="";
  sections.forEach((section,index)=>{
    const button=document.createElement("button");
    button.className="section-button";
    button.dataset.section=section.id;
    button.innerHTML='<span class="section-number">'+(index+1)+'</span><span><strong>'+escapeHtml(section.title)+'</strong><span class="muted" style="display:block">'+escapeHtml(section.prompt)+'</span></span>';
    button.addEventListener("click",()=>teacherAction({type:"set_section",section}));
    el.sectionList.appendChild(button);
  });
}

async function teacherAction(action){
  try{
    await api("./api/teacher/action",{method:"POST",headers:authHeaders,body:JSON.stringify(action)});
    await refresh();
  }catch(error){
    el.connectionBadge.textContent="Action failed";
    alert(error.message);
  }
}

async function refresh(){
  try{
    const payload=await api("./api/teacher/dashboard",{headers:authHeaders});
    state=payload.state;
    events=payload.events||[];
    if(state.questionnaire_definition) questionnaire=state.questionnaire_definition;
    el.connectionBadge.textContent="Connected";
    render();
  }catch(error){
    el.connectionBadge.textContent="Disconnected";
  }
}

function render(){
  el.joinCode.textContent=state.join_code;
  el.studentUrl.textContent=state.student_url;
  const now=Date.now();
  const participants=state.participants||[];
  el.joinedCount.textContent=participants.length;
  el.preCount.textContent=participants.filter(p=>p.pretest_completed).length;
  el.postCount.textContent=participants.filter(p=>p.posttest_completed).length;
  el.activeCount.textContent=participants.filter(p=>p.last_seen && now-new Date(p.last_seen).getTime()<30000).length;
  el.phaseStatus.textContent="Current phase: "+state.phase;
  if(questionnaire) el.questionnaireStatus.textContent="Questionnaire: "+(questionnaire.title||questionnaire.id)+" · "+(questionnaire.version||"unversioned");
  document.querySelectorAll("[data-phase]").forEach(b=>b.classList.toggle("active",b.dataset.phase===state.phase));
  document.querySelectorAll("[data-section]").forEach(b=>b.classList.toggle("active",b.dataset.section===state.section?.id));
  renderLive();
  renderDoubts();
  renderPrePost();
  renderEngagement();
}

function renderLive(){
  const q=questionnaire.live[0];
  el.liveQuestion.innerHTML='<strong>'+escapeHtml(q.prompt)+'</strong><div class="muted">'+q.options.map((o,i)=>(i+1)+". "+escapeHtml(o)).join("<br>")+'</div>';
  const answers=events.filter(e=>e.type==="live_response" && e.payload?.question_id===q.id);
  const counts=q.options.map((_,i)=>answers.filter(a=>a.payload?.answer===i).length);
  const total=counts.reduce((a,b)=>a+b,0);
  el.liveResponses.innerHTML=counts.map((count,i)=>{
    const pct=total?Math.round(count/total*100):0;
    return '<div class="response-bar"><span>'+escapeHtml(q.options[i])+'</span><div class="bar-track"><div class="bar-fill" style="width:'+pct+'%"></div></div><strong>'+count+'</strong></div>';
  }).join("");
  el.openLiveQuestion.disabled=Boolean(state.live_question_id);
  el.closeLiveQuestion.disabled=!state.live_question_id;
}

function renderDoubts(){
  const doubts=events.filter(e=>e.type==="doubt_submitted").slice().reverse();
  if(!doubts.length){el.doubtList.innerHTML='<div class="muted">No doubts submitted yet.</div>';return;}
  const started=new Date(state.started_at).getTime();
  el.doubtList.innerHTML=doubts.map(e=>{
    const elapsed=Math.max(0,Math.round((new Date(e.server_time).getTime()-started)/1000));
    const min=Math.floor(elapsed/60),sec=String(elapsed%60).padStart(2,"0");
    return '<div class="doubt"><strong>'+escapeHtml(e.payload?.text)+'</strong><span class="small">'+min+":"+sec+" · "+escapeHtml(e.section_id||"unassigned")+'</span></div>';
  }).join("");
}

function renderPrePost(){
  const preEvents=events.filter(e=>e.type==="pretest_completed");
  const postEvents=events.filter(e=>e.type==="posttest_completed");
  const preBy=new Map(preEvents.map(e=>[e.participant_id,e]));
  const postBy=new Map(postEvents.map(e=>[e.participant_id,e]));
  const paired=[...preBy.keys()].filter(id=>postBy.has(id));
  if(!paired.length){el.prePostSummary.innerHTML='<div class="muted">Paired pre/post results will appear after students complete both.</div>';return;}
  const concepts=[...new Set(questionnaire.pre.items.map(i=>i.concept_id))];
  el.prePostSummary.innerHTML=concepts.map(concept=>{
    const preItem=questionnaire.pre.items.find(i=>i.concept_id===concept);
    const postItem=questionnaire.post.items.find(i=>i.concept_id===concept);
    let preCorrect=0,postCorrect=0;
    paired.forEach(id=>{
      if(preBy.get(id).payload?.responses?.[preItem.id]===preItem.correct)preCorrect++;
      if(postBy.get(id).payload?.responses?.[postItem.id]===postItem.correct)postCorrect++;
    });
    return '<div class="response-bar"><span>'+escapeHtml(concept.replaceAll("_"," "))+'</span><div class="bar-track"><div class="bar-fill" style="width:'+Math.round(postCorrect/paired.length*100)+'%"></div></div><strong>'+preCorrect+"→"+postCorrect+'</strong></div>';
  }).join("");
}

function renderEngagement(){
  const participants=state.participants||[];
  if(!participants.length){el.engagementSummary.innerHTML='<div class="muted">No participants yet.</div>';return;}
  el.engagementSummary.innerHTML=participants.slice(0,50).map(p=>{
    const sectionCount=new Set(events.filter(e=>e.participant_id===p.id && e.type==="section_viewed").map(e=>e.section_id)).size;
    const pings=events.filter(e=>e.participant_id===p.id && e.type==="engagement_ping" && e.payload?.visible).length;
    return '<div class="event"><strong>'+escapeHtml(p.label||p.id.slice(0,8))+'</strong><span class="small">'+sectionCount+"/3 sections viewed · "+pings+" visible activity pings</span></div>";
  }).join("");
}


function validateQuestionnaire(definition){
  if(!definition || typeof definition!=="object") throw new Error("questionnaire must be a JSON object");
  if(!definition.id) throw new Error("id is required");
  if(!definition.pre?.items || !Array.isArray(definition.pre.items)) throw new Error("pre.items array is required");
  if(!definition.post?.items || !Array.isArray(definition.post.items)) throw new Error("post.items array is required");
  const all=[...definition.pre.items,...definition.post.items,...(definition.live||[])];
  for(const item of all){
    if(!item.id || !item.prompt) throw new Error("each item needs id and prompt");
    if(item.type==="single_choice"){
      if(!Array.isArray(item.options) || item.options.length<2) throw new Error("single_choice needs options");
      if(!Number.isInteger(item.correct) || item.correct<0 || item.correct>=item.options.length) throw new Error("single_choice needs a valid correct index");
    }
  }
}
