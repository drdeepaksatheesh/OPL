export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type":"application/json", ...(options.headers || {})},
    ...options
  });
  if (!response.ok) {
    let detail = "";
    try { detail = await response.text(); } catch {}
    throw new Error(detail || ("HTTP " + response.status));
  }
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {type:"application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function scoreItems(items, responses) {
  let answered = 0;
  let correct = 0;
  for (const item of items || []) {
    if (responses && Object.prototype.hasOwnProperty.call(responses, item.id)) {
      answered += 1;
      if (responses[item.id] === item.correct) correct += 1;
    }
  }
  return {answered, correct, total:(items || []).length};
}

export function renderQuestion(container, item, selected, onSelect, disabled=false) {
  container.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "question-card";
  const title = document.createElement("h3");
  title.textContent = item.prompt;
  wrap.appendChild(title);
  const options = document.createElement("div");
  options.className = "question-options";
  item.options.forEach((label,index)=>{
    const button = document.createElement("button");
    button.type = "button";
    button.className = "question-option" + (selected === index ? " selected" : "");
    button.textContent = label;
    button.disabled = disabled;
    button.addEventListener("click",()=>onSelect(index));
    options.appendChild(button);
  });
  wrap.appendChild(options);
  container.appendChild(wrap);
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
}

export function formatClock(iso) {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"});
}
