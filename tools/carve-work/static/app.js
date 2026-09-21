'use strict';
const $ = selector => document.querySelector(selector);
const state = {threads: [], tasks: [], files: [], repo: [], settings: {}, current: null, thread: null,
  busy: false, attachments: [], approvals: [], draft: '', activeBubble: null, currentMessage: null};
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const asDate = unix => new Date(unix*1000).toLocaleDateString(undefined, {month:'short', day:'numeric'});
const size = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(1)} MB`;
const timeWait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function request(path, method='GET', data=undefined) {
  const opts = {method, headers: {}};
  if(data !== undefined) {opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data);}
  const resp=await fetch(path,opts);
  const body=await resp.json().catch(()=>({error: `HTTP ${resp.status}`}));
  if(!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
  return body;
}
function toast(message) {const element=$('#toast');element.textContent=message;element.classList.add('show');clearTimeout(element.timer);element.timer=setTimeout(()=>element.classList.remove('show'),5500);}
function showError(message) {$('#errorText').textContent=String(message);$('#errorPanel').classList.remove('hidden');}
function hideError() {$('#errorPanel').classList.add('hidden');}

function scrollBottom() {const el=$('#chatScroller');el.scrollTop=el.scrollHeight;}
function renderMarkdown(source) {
  const text=String(source ?? '');
  const code=[];
  let escaped=escapeHTML(text).replace(/```([^\n`]*)\n([\s\S]*?)```/g,(_all,lang,contents)=>{
    let key=`__CODEBLOCK_${code.length}__`;
    code.push(`<pre><code>${contents}</code></pre>`);return key;
  });
  let html=escaped.split('\n').map(line=>{
    if(/^#{1,3}\s/.test(line)) {let h=line.match(/^#+/)[0].length;return `<h${h}>${line.slice(h+1)}</h${h}>`;}
    if(/^\s*[-*]\s/.test(line))return `<p>• &nbsp;${line.replace(/^\s*[-*]\s/,'')}</p>`;
    if(/^\d+\.\s/.test(line))return `<p>${line}</p>`;
    if(!line.trim())return '<br>';
    return `<p>${line}</p>`;
  }).join('');
  html=html.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>');
  html=html.replace(/__CODEBLOCK_(\d+)__/g,(_,i)=>code[Number(i)]||'');
  return html;
}
function message(role, content='', extra={}) {
  if(role==='handoff') {
    const box=document.createElement('div');box.className='handover';
    box.innerHTML=`<h3>↗ Automatic conversation handover</h3><small>Full previous chat is preserved in the sidebar.</small><details><summary>Read handover statement</summary><div class="content">${renderMarkdown(content)}</div></details>`;
    $('#messages').append(box);scrollBottom();return box;
  }
  const el=document.createElement('section');el.className=`message ${role}`;
  const label=role==='user'?'YOU':'CARVEWORK';
  el.innerHTML=`<div class="avatar">${role==='user'?'U':'◈'}</div><div class="bubble"><div class="who">${label}</div><div class="content"></div></div>`;
  $('#messages').append(el);
  el.querySelector('.content').innerHTML=renderMarkdown(content);
  scrollBottom();return el;
}
function updateMessage(element, text) {if(!element)return;element.querySelector('.content').innerHTML=renderMarkdown(text);scrollBottom();}
function renderThreads() {
  const list=$('#threads');list.replaceChildren();$('#threadCount').textContent=state.threads.length;
  for(const t of state.threads) {
    const b=document.createElement('button');b.className='thread'+(t.id===state.current?' active':'');
    b.innerHTML=`<div class="threadtitle">${escapeHTML(t.title||'New chat')}</div><div class="threadmeta"><span>${asDate(t.created)}</span><span>· ${t.turns} turns</span>${t.previous_id?'<span class="continued"> ↗ continued</span>':''}${t.archived?'<span>· archived</span>':''}</div>`;
    b.addEventListener('click',()=>selectThread(t.id));list.append(b);
  }
}
function renderTasks(){const list=$('#tasks');list.replaceChildren();if(!state.tasks.length){list.innerHTML='<div class="empty">Tasks you create here or through chat appear here.</div>';return;}
  for(const task of state.tasks) {const el=document.createElement('div');el.className='task'+(task.done?' done':'');
    const box=document.createElement('input');box.type='checkbox';box.checked=!!task.done;box.disabled=!!task.done;box.title='Mark task completed';
    box.addEventListener('change',async()=>{try{await request('/api/task/complete','POST',{id:task.id});await refresh();}catch(e){toast(e.message)}});
    const label=document.createElement('label');label.textContent=task.title;label.title=task.details||'';label.addEventListener('click',()=>{if(task.details)toast(task.details)});
    el.append(box,label);list.append(el);
  }
}
function renderFiles(target, files, limit=25){const list=$(target);list.replaceChildren();if(!files.length){list.innerHTML='<span class="empty">No files yet</span>';return;}
  for(const file of files.slice(0,limit)) {const b=document.createElement('button');b.className='file';
    b.innerHTML=`<span>▤</span><span class="filename" title="${escapeHTML(file.path)}">${escapeHTML(file.path.split('/').slice(1).join('/'))}</span><span class="size">${size(file.bytes)}</span>`;
    b.addEventListener('click',()=>showFile(file.path));list.append(b);
  }
  if(files.length>limit){const x=document.createElement('div');x.className='micro';x.textContent=`Showing first ${limit} of ${files.length} files; use the chat search_files tool for others.`;list.append(x)}
}
function renderStatus(){const t=state.thread||{};const turns=state.threads.find(x=>x.id===state.current)?.turns||0;const ctx=state.settings;
  const chars=(t.messages||[]).filter(m=>['assistant','user'].includes(m.role)).reduce((n,m)=>n+m.content.length,0);
  const approx=Math.round(chars/3+500);const pct=Math.min(100,Math.max(turns/Math.max(1,ctx.max_turns||36),approx/Math.max(1,Math.min((ctx.soft_tokens||12000),(ctx.provider==='ollama'?Math.max(1200,(ctx.ollama_ctx||16384)-4000):500000))*.76))*100);
  $('#contextMeter').style.width=pct+'%';$('#contextLabel').textContent=`${turns}/${ctx.max_turns||36} turns`;$('#tokenLabel').textContent=`~${approx.toLocaleString()} / ${ctx.provider==='ollama'?Math.min(ctx.soft_tokens||12000,Math.max(1200,(ctx.ollama_ctx||16384)-4000)):ctx.soft_tokens||12000} est. tokens`;
  $('#threadTitle').textContent=t.title||'New conversation';document.title=(t.title||'CarveWork')+' — CarveWork';
  const local=ctx.provider!=='openai';
  $('#modelTag').textContent=(local?'LOCAL · ':'OPENAI · ')+(ctx.model||'MODEL');
  let status='';let ready=false;
  if(local){ready=!!state.ollama?.online&&!!state.ollama?.installed;
    status=ready?'OLLAMA READY':state.ollama?.online?'MODEL NOT INSTALLED':'OLLAMA OFFLINE';}
  else {ready=!!state.has_api_key;status=ready?'KEY SET · CREDITS UNVERIFIED':'API KEY NEEDED';}
  $('#keyTag').textContent=status;$('#keyTag').title=local?(state.ollama?.message||''):
    'API key configured only; model access and available credits are not verified';
  $('#keyTag').className='tag '+(ready?'good':'bad');
  $('#providerNote').textContent=local?'Ollama local AI · no OpenAI API charges':
    'OpenAI API active · separately billed';
  $('#repoInfo').textContent=state.repo_path||'No local repository linked';$('#repoCount').textContent=state.repo.length?state.repo.length+' files':'';
  const archived=!!t.archived;
  $('#send').disabled=state.busy||archived;$('#prompt').disabled=state.busy||archived;
  $('#prompt').placeholder=archived?'Archived—select the newer conversation in the sidebar':'Ask CarveWork anything about your project…';
  $('#rolloverNow').disabled=state.busy||archived;
}
async function refresh(){const s=await request('/api/state');Object.assign(state,s);renderThreads();renderTasks();renderFiles('#files',state.workspace);renderFiles('#repoFiles',state.repo,20);renderStatus();}
async function selectThread(id){if(state.busy)return;state.current=id;localStorage.setItem('carvework.thread',id);state.thread=await request('/api/thread?id='+encodeURIComponent(id));
  $('#messages').replaceChildren();$('#welcome').classList.toggle('hidden',state.thread.messages.length>0);
  for(const m of state.thread.messages)message(m.role,m.content);scrollBottom();renderThreads();renderStatus();}
async function createChat(){if(state.busy)return;const result=await request('/api/thread','POST',{title:'New chat'});await refresh();await selectThread(result.thread_id);$('#prompt').focus();}
async function manualRollover(){if(state.busy)return;if(!confirm('Create a handover and start a linked continuation? The full old chat will remain available.'))return;
  state.busy=true;$('#thinking').classList.remove('hidden');$('#thinkingText').textContent='Preparing a handover…';renderStatus();
  try{const result=await request('/api/rollover','POST',{thread_id:state.current});await refresh();await selectThread(result.thread_id);toast('Continuation created. Your previous chat is preserved.');}
  catch(e){toast(e.message)}finally{state.busy=false;$('#thinking').classList.add('hidden');renderStatus()}}
async function showFile(path){state.openFile=path;$('#fileEditor').classList.add('hidden');$('#fileSave').classList.add('hidden');$('#fileEdit').classList.toggle('hidden',!path.startsWith('workspace/'));$('#fileContents').classList.remove('hidden');$('#fileBackdrop').classList.remove('hidden');$('#fileTitle').textContent=path;
  $('#fileContents').textContent='Loading file…';$('#downloadFile').href='/api/raw?path='+encodeURIComponent(path);
  if(/\.(png|webp|jpg|jpeg|gif|svg)$/i.test(path)) {
    $('#fileContents').textContent='Image preview:';let img=document.createElement('img');img.src=$('#downloadFile').href;img.style.cssText='max-width:100%;max-height:60vh;display:block;margin-top:12px;';$('#fileContents').append(img);return;
  }
  try{$('#fileContents').textContent=(await request('/api/file?path='+encodeURIComponent(path))).text}
  catch(e){$('#fileContents').textContent=e.message+'\nUse Download/open to access large or non-text files.'}
}
async function uploadFiles(files){const processed=[];
  for(const file of Array.from(files).slice(0,6)){
    if(file.size>3*1024*1024){toast(file.name+': maximum 3 MB');continue;}
    const raw=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Cannot read file'));reader.readAsDataURL(file)});
    const res=await request('/api/upload','POST',{name:file.name,base64:raw});processed.push(res.path);
  }
  state.attachments.push(...processed);renderAttachments();await refresh();if(processed.length)toast(`${processed.length} file(s) saved in workspace`);
}
function renderAttachments(){const wrap=$('#attachments');wrap.replaceChildren();wrap.classList.toggle('hidden',!state.attachments.length);
  for(const path of state.attachments){const tag=document.createElement('span');tag.className='attach';tag.append(document.createTextNode(path.split('/').pop()+' '));const del=document.createElement('button');del.textContent='×';del.title='Remove from this message';del.onclick=()=>{state.attachments=state.attachments.filter(x=>x!==path);renderAttachments()};tag.append(del);wrap.append(tag)}
}
async function approve(choice){const first=state.approvals.shift();if(!first)return;
  try{await request('/api/approval','POST',{id:first.id,approve:choice})}catch(e){toast(e.message)}
  $('#approvalBackdrop').classList.add('hidden');showNextApproval();}
function showNextApproval(){if(!state.approvals.length){$('#approvalBackdrop').classList.add('hidden');return}
  const a=state.approvals[0];$('#approvalTitle').textContent=a.name;$('#approvalDetails').textContent=a.details;$('#approvalBackdrop').classList.remove('hidden');}
async function sendMessage(custom){if(state.busy||state.thread?.archived)return;
  const text=custom!==undefined?custom:$('#prompt').value;const attaches=[...state.attachments];
  if(!text.trim()&&!attaches.length)return;
  state.busy=true;renderStatus();$('#prompt').value='';state.attachments=[];renderAttachments();$('#welcome').classList.add('hidden');
  const displayed=text.trim()+attaches.map(x=>'\n[Attached image/file: '+x+']').join('');
  const imagePaths=attaches.filter(x=>/\.(png|jpe?g|gif|webp)$/i.test(x));
  const nonImagePaths=attaches.filter(x=>!imagePaths.includes(x));
  const messageText=text.trim()+nonImagePaths.map(x=>'\n[Uploaded project file available via read_file: '+x+']').join('');
  message('user',displayed);
  state.activeBubble=message('assistant','');let answer='';const thinking=$('#thinking');thinking.classList.remove('hidden');$('#thinkingText').textContent='Connecting to the model…';
  let success=false;let activeId=state.current;
  try{
    const res=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({thread_id:state.current,text:messageText,attachments:imagePaths})});
    if(!res.ok)throw Error((await res.json()).error||'Server rejected request');
    const reader=res.body.getReader();const dec=new TextDecoder();let buffer='';
    const handle=(block)=>{
      const kind=(block.match(/^event: (.*)$/m)||[])[1];const lines=block.split('\n').filter(x=>x.startsWith('data: '));if(!lines.length)return;
      const value=JSON.parse(lines.map(x=>x.slice(6)).join('\n'));
      if(kind==='delta'){answer+=value.text;updateMessage(state.activeBubble,answer);$('#thinkingText').textContent='Generating response…'}
      else if(kind==='activity'){$('#thinkingText').textContent=value.text}
      else if(kind==='approval'){state.approvals.push(value);showNextApproval();$('#thinkingText').textContent='Waiting for approval…'}
      else if(kind==='rollover'){
        activeId=value.thread_id;state.current=activeId;localStorage.setItem('carvework.thread',activeId);
        $('#messages').replaceChildren();message('handoff',value.handover);message('user',displayed);
        state.activeBubble=message('assistant',answer);toast('Chat continued automatically with a handover.');}
      else if(kind==='done'){success=true;activeId=value.thread_id;answer=value.text;updateMessage(state.activeBubble,answer)}
      else if(kind==='error')throw Error(value.message);
    };
    while(true){const {done,value}=await reader.read();if(done)break;buffer+=dec.decode(value,{stream:true});let at;
      while((at=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,at).replace(/\r/g,'');buffer=buffer.slice(at+2);handle(block)}
    }
    if(!success)throw Error('Response interrupted. Reopen the conversation to check what was saved.');
  }catch(e){if(state.activeBubble)updateMessage(state.activeBubble,answer+'\n\n[Error: '+e.message+']');showError(e.message);toast('Chat error — details retained above the message box.')}
  finally{state.busy=false;thinking.classList.add('hidden');await refresh().catch(()=>{});await selectThread(activeId).catch(()=>{});$('#prompt').focus();scrollBottom()}
}
async function initialize(){try{await refresh();const stored=localStorage.getItem('carvework.thread');await selectThread(state.threads.some(x=>x.id===stored)?stored:state.threads[0].id);
  $('#settingsOpen').addEventListener('click',showSettings);$('#newChat').addEventListener('click',createChat);$('#rolloverNow').addEventListener('click',manualRollover);
  $('#send').addEventListener('click',()=>sendMessage());$('#prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}});
  $('#upload').addEventListener('change',async e=>{try{await uploadFiles(e.target.files)}catch(err){toast(err.message)}e.target.value=''});
  for(const b of document.querySelectorAll('.suggest'))b.onclick=()=>sendMessage(b.dataset.prompt);
  $('#acceptApproval').addEventListener('click',()=>approve(true));$('#rejectApproval').addEventListener('click',()=>approve(false));
  $('#addTask').addEventListener('click',async()=>{const title=prompt('New task title:');if(!title?.trim())return;try{await request('/api/task','POST',{title});await refresh()}catch(e){toast(e.message)}});
  $('#toggleRight').onclick=()=>document.body.classList.toggle('hide-right');$('#closeRight').onclick=()=>document.body.classList.add('hide-right');
  $('#settingsClose').onclick=$('#settingsCancel').onclick=()=>$('#settingsBackdrop').classList.add('hidden');
  $('#settingsSave').onclick=async()=>{try{state.settings=await request('/api/settings','POST',{
    provider:$('#settingProvider').value,model:$('#settingModel').value,ollama_ctx:Number($('#settingOllamaCtx').value),soft_tokens:Number($('#settingTokens').value),max_turns:Number($('#settingTurns').value),web_search:$('#settingProvider').value==='openai'&&$('#settingWeb').checked?1:0});
    $('#settingsBackdrop').classList.add('hidden');await refresh();renderStatus();toast('Settings saved')}
    catch(e){showError(e.message);toast('Settings error — see retained details.')}};
  $('#fileClose').onclick=$('#fileDone').onclick=()=>$('#fileBackdrop').classList.add('hidden');
  $('#fileEdit').onclick=()=>{$('#fileEditor').value=$('#fileContents').textContent;$('#fileContents').classList.add('hidden');$('#fileEditor').classList.remove('hidden');$('#fileSave').classList.remove('hidden');$('#fileEdit').classList.add('hidden')};
  $('#fileSave').onclick=async()=>{try{await request('/api/file/save','POST',{path:state.openFile,content:$('#fileEditor').value});await refresh();toast('Workspace file saved');showFile(state.openFile)}catch(e){toast(e.message)}};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!state.approvals.length){$('#settingsBackdrop').classList.add('hidden');$('#fileBackdrop').classList.add('hidden')}});
  window.addEventListener('dragover',e=>e.preventDefault());window.addEventListener('drop',async e=>{e.preventDefault();if(e.dataTransfer?.files?.length){try{await uploadFiles(e.dataTransfer.files)}catch(err){toast(err.message)}}});
  $('#copyError').onclick=async()=>{try{await navigator.clipboard.writeText($('#errorText').textContent);toast('Error copied.')}catch(e){toast('Select the error text to copy it manually.')}};
  $('#closeError').onclick=hideError;
  $('#settingProvider').onchange=()=>{const provider=$('#settingProvider').value;
    $('#settingModel').value=provider==='ollama'?(state.settings.ollama_model||'devstral-small-2:24b'):
      (state.settings.openai_model||'gpt-5.6-terra');renderProviderSettings();};
  if(state.settings.provider==='ollama'&&!state.ollama?.installed)toast(state.ollama?.message||'Ollama is not ready.');
  if(state.settings.provider==='openai'&&!state.has_api_key)toast('Set OPENAI_API_KEY to use the paid OpenAI provider.');
}catch(e){toast('Cannot start CarveWork: '+e.message);console.error(e)}}
function renderProviderSettings(){const local=$('#settingProvider').value==='ollama';
  $('#settingContextRow').classList.toggle('hidden',!local);
  $('#settingWebRow').classList.toggle('hidden',local);
  $('#settingProviderStatus').textContent=local?(state.ollama?.message||'Start Ollama, then download the local model.'):
    'Explicitly selecting OpenAI activates separately billed API requests; no automatic fallback to paid API.';
  const names=state.ollama?.models||[];
  $('#installedModels').replaceChildren();if(local){for(const name of names){const opt=document.createElement('option');opt.value=name;$('#installedModels').append(opt)}}}
function showSettings(){const prefs=state.settings;$('#settingProvider').value=prefs.provider||'ollama';$('#settingModel').value=prefs.model||'devstral-small-2:24b';$('#settingOllamaCtx').value=prefs.ollama_ctx||16384;$('#settingTokens').value=prefs.soft_tokens||12000;$('#settingTurns').value=prefs.max_turns||36;$('#settingWeb').checked=!!prefs.web_search;renderProviderSettings();$('#settingsBackdrop').classList.remove('hidden')}

initialize();
