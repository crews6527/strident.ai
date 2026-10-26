'use strict';
const $=id=>document.getElementById(id);
let selected='',lastSeq=0,tasks=[],polling=false,account=null;
sessionStorage.removeItem('strident-key');
const fragment=new URLSearchParams(location.hash.slice(1));
if(fragment.has('key')){$('key').value=fragment.get('key');history.replaceState(null,'',location.pathname);}
async function api(path,body){
 const r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Strident-Request':'1','X-Strident-CSRF':account?.csrf||''},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const data=await r.json();if(!r.ok){if(r.status===401){account=null;connected(false);}throw Error(data.error||'Request failed');}return data;
}
function notice(message){$('notice').textContent=message;}
function connected(ok){document.body.classList.toggle('disconnected',!ok);$('auth').hidden=ok;document.querySelector('main').hidden=!ok;$('accountBar').hidden=!ok;$('connection').textContent=ok?'Signed in':'Login required';if(ok){const admin=account.role==='admin';$('accountName').textContent=account.username+' ('+account.role+')';$('logout').textContent=admin?'Admin logout':'User logout';$('settingsToggle').hidden=!admin;$('userAdmin').hidden=!admin;$('deleteAccount').hidden=admin;document.querySelector('.suggestions').hidden=!admin;}}
function pick(id){selected=id;lastSeq=0;$('events').replaceChildren();render();poll();}
function render(){
 $('history').replaceChildren();for(const t of tasks){let b=document.createElement('button');if(t.id===selected)b.className='selected';let title=document.createElement('div');title.textContent=t.prompt.slice(0,90);let sub=document.createElement('small');sub.textContent=t.status+' · '+new Date(t.created*1000).toLocaleTimeString();b.append(title,sub);b.onclick=()=>pick(t.id);$('history').append(b);}
 const t=tasks.find(t=>t.id===selected);$('task').hidden=!t;if(!t)return;
 $('taskTitle').textContent=t.prompt==='/testmodel'?'Model generation test':t.prompt.slice(0,120);
 $('status').textContent=t.status;$('result').textContent=t.result||'Waiting for output…';$('error').textContent=t.error;
 $('time').textContent='Task '+t.id+' · '+Math.max(0,Math.round(((t.status==='running'?Date.now()/1000:t.updated)-t.created)))+' seconds since submission';
 $('cancel').disabled=!['running','queued'].includes(t.status);$('retry').disabled=['running','queued'].includes(t.status);
}
async function poll(){if(polling||!account)return;polling=true;try{
 tasks=await api('tasks');connected(true);if(!selected&&tasks.length)selected=tasks[0].id;render();
 if(selected){let more=true;let batches=0;while(more&&batches++<4){const events=await api('events?task='+encodeURIComponent(selected)+'&after='+lastSeq);for(const ev of events){lastSeq=ev.seq;if(['delta','model_progress'].includes(ev.kind))continue;let d=document.createElement('div');d.className='event';let label=document.createElement('strong');label.textContent=ev.kind.replaceAll('_',' ')+' · '+new Date(ev.created*1000).toLocaleTimeString();let p=document.createElement('pre');p.textContent=JSON.stringify(ev.payload,null,2);d.append(label,p);$('events').append(d);}more=events.length===500;}}
 }catch(e){connected(false);notice(e.message);}finally{polling=false;}}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{account=await api('login',{username:$('username').value,password:$('password').value});$('password').value='';$('authNotice').textContent='';connected(true);poll();}catch(err){$('authNotice').textContent=err.message;}};
$('setupForm').onsubmit=async e=>{e.preventDefault();try{account=await api('bootstrap',{key:$('key').value,username:$('setupName').value,password:$('setupPassword').value});$('key').value='';$('setupPassword').value='';connected(true);poll();}catch(err){$('authNotice').textContent=err.message;}};
function clearSession(){account=null;tasks=[];selected='';lastSeq=0;$('events').replaceChildren();$('history').replaceChildren();$('result').textContent='';$('settings').hidden=true;connected(false);}
$('logout').onclick=async()=>{try{await api('logout',{});clearSession();}catch(e){notice(e.message);}};
$('createUserForm').onsubmit=async e=>{e.preventDefault();try{await api('users',Object.fromEntries(new FormData(e.target)));e.target.reset();notice('User created. Share credentials privately.');}catch(e){notice(e.message);}};
$('deleteAccount').onclick=async()=>{if(!confirm('Permanently delete this account, task history and local data?'))return;try{await api('delete-account',{confirmation:'DELETE'});clearSession();}catch(e){notice(e.message);}};
$('refresh').onclick=poll;
$('taskForm').onsubmit=async e=>{e.preventDefault();$('send').disabled=true;try{const r=await api('tasks',{prompt:$('prompt').value});$('prompt').value='';notice('Task queued in the shared desktop agent. Progress and tool results appear below.');pick(r.id);}catch(e){notice(e.message);}finally{$('send').disabled=false;}};
for(const b of document.querySelectorAll('[data-command]'))b.onclick=()=>{$('prompt').value=b.dataset.command;$('prompt').focus();};
$('cancel').onclick=async()=>{try{await api('cancel',{id:selected});notice('Cancellation requested. Completed actions remain in the evidence.');poll();}catch(e){notice(e.message);}};
$('retry').onclick=async()=>{if(!confirm('Retry may repeat completed actions. Review the evidence first. Run this task again?'))return;try{const r=await api('retry',{id:selected});pick(r.id);}catch(e){notice(e.message);}};
$('export').onclick=async()=>{try{const data=await api('export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='Strident-Transcript.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Transcript exported. It contains task text, local paths and results. Review it before sharing.');}catch(e){notice(e.message);}};
async function settings(){try{const c=await api('config');for(const el of $('settingsForm').elements)if(el.name)el.value=c[el.name]??'';$('budget').textContent='Overall task budget: '+c.max_task_seconds+'s · Worker idle limit: '+c.task_timeout+'s';$('settings').hidden=false;}catch(e){notice(e.message);}}
$('settingsToggle').onclick=settings;$('closeSettings').onclick=()=>{$('settings').hidden=true;};
$('settingsForm').onsubmit=async e=>{e.preventDefault();const c={};for(const el of e.target.elements)if(el.name)c[el.name]=el.type==='number'?Number(el.value):el.value;c.text_model='';try{await api('config',c);notice('Settings saved. Test the saved model before submitting writing tasks.');settings();}catch(e){notice(e.message);}};
$('models').onclick=async()=>{try{const d=await api('models');$('modelList').replaceChildren();for(const m of d.models){const o=document.createElement('option');o.value=m.name;o.label=m.name+' ('+m.size_gb+' GB)';$('modelList').append(o);}notice(d.models.length?d.models.map(m=>m.name+' · '+m.size_gb+' GB').join('\n'):'No models installed in Ollama. Install a model on the PC first.');}catch(e){notice(e.message);}};
$('testModel').onclick=async()=>{try{const r=await api('test-model',{});pick(r.id);notice('Testing real generation with the saved model. Inspect timings and any error below.');}catch(e){notice(e.message);}};
connected(false);api('me').then(a=>{account=a;connected(true);poll();}).catch(()=>{});setInterval(poll,1000);

$('passwordForm').onsubmit=async e=>{e.preventDefault();try{await api('change-password',Object.fromEntries(new FormData(e.target)));e.target.reset();clearSession();$('authNotice').textContent='Password changed. Log in with your new password.';}catch(e){notice(e.message);}};
