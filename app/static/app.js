const $=s=>document.querySelector(s), form=$('#proposalForm');
let currentId=null, timer, quoteSequence=0;
const currency=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(v);
const numeric=new Set(['users','workstations','servers','term_months','renewal_months','notice_days']);
const moneyFields=new Set(['user_rate','workstation_rate','server_rate','onboarding','discount','tax_percent','hourly_rate','after_hours_rate']);
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Phoenix',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,method='GET',data){
 const response=await fetch(url,{method,headers:{'Content-Type':'application/json','X-TLIT-Request':'1'},body:data===undefined?undefined:JSON.stringify(data)});
 if(!response.ok){let e=await response.json();if(response.status===401&&url!='/api/login')showLogin();throw Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail));}return response;
}
function message(text,error=false){$('#message').textContent=text;$('#message').classList.toggle('error',error);}
function showLogin(){$('#login').hidden=false;$('#studio').hidden=true;}
async function showStudio(username){$('#login').hidden=true;$('#studio').hidden=false;$('#who').textContent=username;await refreshList();scheduleQuote();}
$('#loginForm').onsubmit=async e=>{e.preventDefault();try{const user=await(await api('/api/login','POST',Object.fromEntries(new FormData(e.target)))).json();e.target.reset();$('#loginError').textContent='';await showStudio(user.username);}catch(e){$('#loginError').textContent=e.message;}};
$('#logout').onclick=async()=>{try{await api('/api/logout','POST');showLogin();}catch(e){message(e.message,true);}};
for(const [key,label,placeholder] of [['cloud','Cloud services','Microsoft 365, Google Workspace, Azure, AWS...'],['domain','Identity / domain controller','Active Directory, Entra ID, local accounts...'],['backups','Backups & recovery','Provider, scope, retention, last restore test...'],['security','Security posture','Endpoint, email, MFA, MDR...'],['applications','Business applications','Critical apps, vendors, integrations...'],['needs','Business needs & pain points','Support experience, downtime, priorities...'],['recommendations','Proposed approach','What should change and why?']]){
 $('#discoveryFields').insertAdjacentHTML('beforeend',`<label class="${key==='recommendations'?'full':''}">${label}<textarea name="${key}" maxlength="2000" rows="3" placeholder="${placeholder}"></textarea></label>`);
}
function field(label,key,value,type='text',options=null,max=200){
 let control=options?`<select data-key="${key}">${options.map(v=>`<option ${value===v?'selected':''}>${escapeHtml(v)}</option>`).join('')}</select>`:`<input data-key="${key}" type="${type}" ${type==='checkbox'?(value?'checked':''):`value="${escapeHtml(value)}"`} ${type==='number'?'min="0" max="1000000" step="'+(key==='quantity'?'1':'0.01')+'"':`maxlength="${max}"`}>`;
 return `<label>${label}${control}</label>`;
}
function addRow(kind,data={}){
 const row=document.createElement('div');row.className='dynamic-row '+(kind==='services'?'service-row':kind==='extras'?'extra-row':'');
 if(kind==='assets')row.innerHTML=field('Type','kind',data.kind||'Workstation','text',['Workstation','Physical server','Cloud server','Firewall','Switch','Access point','Other'])+field('Description','description',data.description||'')+field('Qty','quantity',data.quantity??1,'number')+field('Location / cloud','location',data.location||'');
 if(kind==='extras')row.innerHTML=field('Charge','description',data.description||'','text',null,150)+field('Qty','quantity',data.quantity??1,'number')+field('Unit rate','rate',data.rate??0,'number')+field('Cadence','cadence',data.cadence||'monthly','text',['monthly','one-time'])+field('Taxable','taxable',data.taxable||false,'checkbox');
 if(kind==='services')row.innerHTML=field('Service','description',data.description||'','text',null,350)+field('Frequency','frequency',data.frequency||'Ongoing','text',null,80)+field('Coverage','status',data.status||'Included','text',['Included','Excluded','Not applicable']);
 const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove row');remove.onclick=()=>{row.remove();dirty();scheduleQuote();};row.append(remove);$('#'+kind).append(row);
}
$('#addAsset').onclick=()=>{addRow('assets');dirty();};$('#addExtra').onclick=()=>{addRow('extras');dirty();};$('#addService').onclick=()=>{addRow('services');dirty();};
function collect(){
 const data={};for(const el of form.elements){if(!el.name)continue;data[el.name]=el.type==='checkbox'?el.checked:numeric.has(el.name)?Number(el.value):moneyFields.has(el.name)?(el.value||'0'):el.value;}
 for(const date of ['effective_date','msa_date'])if(!data[date])data[date]=null;
 for(const kind of ['assets','extras','services'])data[kind]=[...$('#'+kind).children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-key]')].map(el=>[el.dataset.key,el.type==='checkbox'?el.checked:el.dataset.key==='quantity'?Number(el.value):el.value])));
 return data;
}
function fill(data){
 form.reset();for(const el of form.elements){if(!el.name)continue;if(data[el.name]!==undefined){if(el.type==='checkbox')el.checked=data[el.name];else el.value=data[el.name]??'';}}
 for(const kind of ['assets','extras','services']){$('#'+kind).replaceChildren();(data[kind]||[]).forEach(x=>addRow(kind,x));}
 scheduleQuote();
}
function dirty(){$('#draftState').textContent=(currentId?'Saved proposal':'New proposal')+' · unsaved changes';$('#exportState').textContent='';}
form.addEventListener('input',()=>{dirty();scheduleQuote();});form.addEventListener('change',scheduleQuote);form.onsubmit=e=>e.preventDefault();
function scheduleQuote(){clearTimeout(timer);timer=setTimeout(updateQuote,250);}
async function updateQuote(){
 const seq=++quoteSequence,data=collect();$('#summaryClient').textContent=data.client||'New client';if(!data.client)data.client='New client';
 try{const q=await(await api('/api/quote','POST',data)).json();if(seq!==quoteSequence)return;
  $('#monthly').textContent=currency(q.monthly);$('#once').textContent=currency(q.one_time);$('#first').textContent=currency(q.first_month);$('#term').textContent=currency(q.term_total);
  $('#breakdown').innerHTML=q.lines.filter(x=>x.cadence==='monthly').map(x=>`<div class="sumrow"><span>${escapeHtml(x.description)}</span><strong>${currency(x.total)}</strong></div>`).join('')+`<div class="sumrow"><span>Discount</span><strong>−${currency(q.discount)}</strong></div><div class="sumrow"><span>Monthly tax</span><strong>${currency(q.tax)}</strong></div>`;
  $('#warnings').innerHTML=q.warnings.map(w=>`<div class="warning">${escapeHtml(w)}</div>`).join('');
 }catch(e){if(seq===quoteSequence){$('#monthly').textContent='—';$('#warnings').textContent=e.message;}}
}
async function refreshList(){const saved=await(await api('/api/proposals')).json();$('#saved').replaceChildren();for(const p of saved){const b=document.createElement('button');b.textContent=p.client;b.title=p.updated;b.onclick=async()=>{if(!canReplace())return;try{fill(await(await api('/api/proposals/'+p.id)).json());currentId=p.id;$('#draftState').textContent='Saved proposal';message('Draft loaded.');}catch(e){message(e.message,true);}};$('#saved').append(b);}}
function canReplace(){return !$('#draftState').textContent.includes('unsaved changes')||confirm('Discard unsaved changes?');}
$('#new').onclick=()=>{if(!canReplace())return;currentId=null;fill({proposal_date:today()});$('#draftState').textContent='New proposal · not saved';message('');};
$('#example').onclick=async()=>{if(!canReplace())return;try{fill(await(await api('/api/example')).json());currentId=null;dirty();message('Reference example loaded. Review the open questions before sending.');}catch(e){message(e.message,true);}};
$('#loadScope').onclick=async()=>{if($('#services').children.length&&!confirm('Replace the current scope with the reference scope?'))return;try{$('#services').replaceChildren();(await(await api('/api/services')).json()).forEach(s=>addRow('services',s));dirty();scheduleQuote();}catch(e){message(e.message,true);}};
$('#save').onclick=async()=>{if(!form.reportValidity())return;try{const r=await(await api(currentId?'/api/proposals/'+currentId:'/api/proposals',currentId?'PUT':'POST',collect())).json();currentId=r.id;$('#draftState').textContent='All changes saved';message('Draft saved.');await refreshList();}catch(e){message(e.message,true);}};
$('#generate').onclick=async()=>{if(!form.reportValidity())return;const button=$('#generate');button.disabled=true;$('#exportState').textContent='Building your PowerPoint and services agreement…';try{const r=await api('/api/generate','POST',collect()),blob=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='TeamLogic-Proposal.zip';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),30000);$('#exportState').textContent='Download ready. Includes PPTX, PDF, proposal data and a review manifest.';}catch(e){$('#exportState').textContent=e.message;}finally{button.disabled=false;}};
window.addEventListener('beforeunload',e=>{if($('#draftState').textContent.includes('unsaved changes')){e.preventDefault();e.returnValue='';}});
fill({proposal_date:today()});api('/api/me').then(r=>r.json()).then(u=>showStudio(u.username)).catch(()=>showLogin());
