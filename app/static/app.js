const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)], form=$('#proposalForm');
let currentId=null, currentVersion=null, timer, quoteSequence=0, writing=false, lastQuote=null;
const currency=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(v);
const numeric=new Set(['users','workstations','servers','networks','mobile_devices','term_months','renewal_months','notice_days']);
const moneyFields=new Set(['user_rate','workstation_rate','server_rate','onboarding','discount','tax_percent','hourly_rate','after_hours_rate']);
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Phoenix',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const BILLING={combined:'Per user + per device',users:'Per user only',devices:'Per workstation / server only'};

// ---------- API ----------
function describe(detail){
 if(typeof detail==='string')return detail;
 if(Array.isArray(detail))return detail.map(x=>((x.loc||[]).filter(l=>l!=='body').join(' › ')||'input')+': '+x.msg).join(' · ');
 return JSON.stringify(detail);
}
async function api(url,method='GET',data,version=null){
 const response=await fetch(url,{method,headers:{'Content-Type':'application/json','X-TLIT-Request':'1',...(version===null?{}:{'If-Match':String(version)})},body:data===undefined?undefined:JSON.stringify(data)});
 if(!response.ok){
  let detail;try{detail=(await response.json()).detail;}catch{detail=null;}
  if(response.status===401&&url!=='/api/login')showLogin();
  throw Error(detail?describe(detail):`Request failed (${response.status}${response.statusText?' '+response.statusText:''}).`);
 }
 return response;
}
function message(text,error=false){$('#message').textContent=text;$('#message').classList.toggle('error',error);}
function showLogin(){$('#login').hidden=false;$('#studio').hidden=true;}
async function showStudio(username){$('#login').hidden=true;$('#studio').hidden=false;$('#who').textContent=username;await refreshList();scheduleQuote();}
$('#loginForm').onsubmit=async e=>{e.preventDefault();try{const user=await(await api('/api/login','POST',Object.fromEntries(new FormData(e.target)))).json();e.target.reset();$('#loginError').textContent='';await showStudio(user.username);}catch(e){$('#loginError').textContent=e.message;}};
$('#logout').onclick=async()=>{try{await api('/api/logout','POST');showLogin();}catch(e){message(e.message,true);}};

// ---------- Discovery fields ----------
const DISCOVERY=[['cloud','Cloud services','Microsoft 365, Google Workspace, Azure, AWS...'],['domain','Identity / domain controller','Active Directory, Entra ID, local accounts...'],['backups','Backups & recovery','Provider, scope, retention, last restore test...'],['security','Security posture','Endpoint, email, MFA, MDR...'],['applications','Business applications','Critical apps, vendors, integrations...'],['needs','Business needs & pain points','Support experience, downtime, priorities...'],['recommendations','Proposed approach','What should change and why?']];
for(const [key,label,placeholder] of DISCOVERY){
 $('#discoveryFields').insertAdjacentHTML('beforeend',`<label class="${key==='recommendations'?'full':''}">${label}<textarea name="${key}" maxlength="2000" rows="3" placeholder="${placeholder}"></textarea></label>`);
}

// ---------- Dynamic rows ----------
const CARDS=[['security','Cybersecurity'],['backup','Backup'],['other','Other']];
const guessCard=d=>/backup/i.test(d||'')?'backup':/secur|protect|mdr|soc\b|endpoint/i.test(d||'')?'security':'other';
function field(label,key,value,type='text',options=null,max=200){
 let control=options?`<select data-key="${key}">${options.map(o=>{const [v,t]=Array.isArray(o)?o:[o,o];return `<option value="${escapeHtml(v)}" ${value===v?'selected':''}>${escapeHtml(t)}</option>`;}).join('')}</select>`:`<input data-key="${key}" type="${type}" ${type==='checkbox'?(value?'checked':''):`value="${escapeHtml(value)}"`} ${type==='number'?'min="0" max="'+(key==='quantity'?'100000':'1000000')+'" step="'+(key==='quantity'?'1':'0.01')+'"':`maxlength="${max}"`}>`;
 return `<label>${label}${control}</label>`;
}
function addRow(kind,data={}){
 const row=document.createElement('div');row.className='dynamic-row '+(kind==='services'?'service-row':kind==='extras'?'extra-row':'');
 if(kind==='assets')row.innerHTML=field('Type','kind',data.kind||'Workstation','text',['Workstation','Physical server','Cloud server','Firewall','Switch','Access point','Other'])+field('Description','description',data.description||'')+field('Qty','quantity',data.quantity??1,'number')+field('Location / cloud','location',data.location||'');
 if(kind==='extras')row.innerHTML=field('Charge','description',data.description||'','text',null,150)+field('Qty','quantity',data.quantity??1,'number')+field('Unit','unit',data.unit??'users','text',null,40)+field('Unit rate','rate',data.rate??0,'number')+field('Cadence','cadence',data.cadence||'monthly','text',['monthly','one-time'])+field('Card','category',data.category??guessCard(data.description),'text',CARDS)+field('Taxable','taxable',data.taxable||false,'checkbox');
 if(kind==='services')row.innerHTML=field('Service','description',data.description||'','text',null,350)+field('Frequency','frequency',data.frequency||'Ongoing','text',null,80)+field('Coverage','status',data.status||'Included','text',['Included','Excluded','Not applicable']);
 row.querySelectorAll('input[data-key=description]').forEach(el=>el.required=true);
 const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove row');remove.onclick=()=>{row.remove();dirty();scheduleQuote();};row.append(remove);$('#'+kind).append(row);
 return row;
}
$('#addAsset').onclick=()=>{addRow('assets').querySelector('input[data-key=description]').focus();dirty();};
$('#addExtra').onclick=()=>{addRow('extras').querySelector('input[data-key=description]').focus();dirty();};
$('#addService').onclick=()=>{addRow('services').querySelector('input[data-key=description]').focus();dirty();};

// ---------- Form <-> JSON ----------
function collect(){
 const data={};
 for(const el of form.elements){
  if(!el.name)continue;
  if(el.type==='radio'){if(el.checked)data[el.name]=el.value;continue;}
  data[el.name]=el.type==='checkbox'?el.checked:numeric.has(el.name)?Number(el.value):moneyFields.has(el.name)?(el.value||'0'):el.value;
 }
 for(const date of ['effective_date','msa_date'])if(!data[date])data[date]=null;
 for(const kind of ['assets','extras','services'])data[kind]=[...$('#'+kind).children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-key]')].map(el=>[el.dataset.key,el.type==='checkbox'?el.checked:el.dataset.key==='quantity'?Number(el.value):el.value])));
 return data;
}
function fill(data){
 form.reset();
 for(const el of form.elements){
  if(!el.name||data[el.name]===undefined)continue;
  if(el.type==='radio')el.checked=el.value===data[el.name];
  else if(el.type==='checkbox')el.checked=!!data[el.name];
  else el.value=data[el.name]??'';
 }
 for(const kind of ['assets','extras','services']){$('#'+kind).replaceChildren();(data[kind]||[]).forEach(x=>addRow(kind,x));}
 applyBilling();scheduleQuote();
}
function dirty(){$('#draftState').textContent=(currentId?'Saved proposal':'New proposal')+' · unsaved changes';$('#exportState').textContent='';}
const isDirty=()=>$('#draftState').textContent.includes('unsaved changes');
form.addEventListener('input',e=>{dirty();scheduleQuote();if(e.target.name==='billing_mode')applyBilling();refreshStepStates();});
form.addEventListener('change',e=>{scheduleQuote();if(e.target.name==='billing_mode')applyBilling();});
form.onsubmit=e=>e.preventDefault();
form.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.tagName==='INPUT'&&e.target.type!=='checkbox'&&e.target.type!=='radio'){e.preventDefault();if(step<STEPS.length)next();}});

// ---------- Qualifying logic ----------
function billingMode(){return form.elements.billing_mode.value;}
function applyBilling(){
 const mode=billingMode();
 for(const el of $$('[data-billing]'))el.hidden=(el.dataset.billing==='users'&&mode==='devices')||(el.dataset.billing==='devices'&&mode==='users');
 for(const h of $$('[data-hint]'))h.textContent=(h.dataset.hint==='users'&&mode==='devices')||(h.dataset.hint==='devices'&&mode==='users')?'Recorded for reference; not billed under this model.':'Billed monthly at the rate you set in Pricing.';
 renderInventoryCheck();
}
function renderInventoryCheck(){
 const d=collect();const count=kinds=>d.assets.filter(a=>kinds.includes(a.kind)).reduce((s,a)=>s+(a.quantity||0),0);
 const ws=count(['Workstation']),sv=count(['Physical server','Cloud server']);
 const line=(label,have,want)=>`<span class="${have===want?'ok':'bad'}">${label}: ${have} listed / ${want} billed</span>`;
 $('#inventoryCheck').innerHTML=`Billing counts from step 2 — ${line('Workstations',ws,d.workstations)} &nbsp;·&nbsp; ${line('Servers',sv,d.servers)}. <button type="button" class="linklike" data-go="2">Change counts</button>`;
}

// ---------- Wizard ----------
const STEPS=[['client','Client'],['engagement','Engagement'],['discovery','Discovery'],['inventory','Inventory'],['pricing','Pricing'],['scope','Scope'],['review','Review & export']];
let step=1;const visited=new Set([1]);
$('#stepper').innerHTML=STEPS.map(([id,title],i)=>`<li><button type="button" data-go="${i+1}"><span class="dot">${i+1}</span><span class="label">${title}</span></button></li>`).join('');
$('#stepNav').innerHTML=STEPS.map(([id,title],i)=>`<button type="button" class="navlink" data-go="${i+1}"><span class="num">0${i+1}</span>${title}<span class="state" aria-hidden="true"></span></button>`).join('');
function sectionControls(n){const section=$(`.step[data-step="${n}"]`);return [...section.querySelectorAll('input,select,textarea')].filter(el=>{const h=el.closest('[hidden]');return !h||h===section;});}
function firstInvalid(n){return sectionControls(n).find(el=>!el.checkValidity());}
function validateStep(n){const bad=firstInvalid(n);if(!bad)return true;go(n,false);bad.reportValidity();return false;}
function validateAll(){for(let n=1;n<=STEPS.length;n++){if(!validateStep(n))return false;}return true;}
function go(n,check=true){
 n=Math.min(Math.max(1,n),STEPS.length);
 if(check&&n>step&&!validateStep(step))return;
 visited.add(step);visited.add(n);step=n;
 $('#history').hidden=true;$('#wizard').hidden=false;
 for(const s of $$('.step'))s.hidden=Number(s.dataset.step)!==n;
 $('#back').disabled=n===1;$('#next').hidden=n===STEPS.length;
 $('#stepCounter').textContent=`Step ${n} of ${STEPS.length}`;
 $('#headerEyebrow').textContent=(currentId?'EDITING PROPOSAL':'NEW PROPOSAL')+' · STEP '+n+' OF '+STEPS.length;
 $('#headerTitle').textContent=$(`.step[data-step="${n}"] h2`).textContent;
 if(n===4)renderInventoryCheck();
 if(n===STEPS.length)renderRecap();
 refreshStepStates();
 if(location.hash!=='#'+STEPS[n-1][0])history.replaceState(null,'','#'+STEPS[n-1][0]);
 $('main').scrollIntoView({block:'start'});window.scrollTo({top:0});
}
function next(){go(step+1);}
function refreshStepStates(){
 const inHistory=!$('#history').hidden;
 $$('[data-go]').forEach(b=>{
  const n=Number(b.dataset.go);if(!b.closest('#stepper')&&!b.closest('#stepNav'))return;
  const invalid=visited.has(n)&&!!firstInvalid(n);
  b.classList.toggle('current',n===step&&!inHistory);b.classList.toggle('done',visited.has(n)&&n!==step&&!invalid);b.classList.toggle('invalid',invalid);
  b.setAttribute('aria-current',n===step&&!inHistory?'step':'false');
  const st=b.querySelector('.state');if(st)st.textContent=invalid?'!':visited.has(n)&&n!==step?'✓':'';
 });
 $('#navHistory').classList.toggle('current',inHistory);
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-go]');if(b)go(Number(b.dataset.go));});
$('#back').onclick=()=>go(step-1,false);$('#next').onclick=next;
function showHistory(){$('#wizard').hidden=true;$('#history').hidden=false;$('#headerEyebrow').textContent='RECORDS';$('#headerTitle').textContent='Version history';refreshStepStates();window.scrollTo({top:0});}
$('#navHistory').onclick=showHistory;$('#backToProposal').onclick=()=>go(step,false);
function startWizard(){visited.clear();visited.add(1);go(1,false);}
function markAllVisited(){for(let n=1;n<=STEPS.length;n++)visited.add(n);}

// ---------- Review recap ----------
function renderRecap(){
 const d=collect(),q=lastQuote;const yes=v=>v?escapeHtml(v):'<em>Not provided</em>';
 const block=(n,title,rows)=>`<section class="recap-block"><header><h3>${title}</h3><button type="button" class="linklike" data-go="${n}">Edit</button></header><dl>${rows.map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></section>`;
 const discovery=DISCOVERY.filter(([k])=>d[k]).map(([k,label])=>[label,escapeHtml(d[k])]);
 const assets=d.assets.length?d.assets.map(a=>`${a.quantity} × ${escapeHtml(a.kind)} — ${escapeHtml(a.description)}${a.location?' ('+escapeHtml(a.location)+')':''}`).join('<br>'):'<em>No equipment listed</em>';
 const CARD={core:'Managed Services',security:'Cybersecurity',backup:'Backup',onboarding:'One-time setup',other:'not on slide'};
 const billed=q?q.lines.map(x=>`${escapeHtml(x.description)}: ${x.quantity} × ${currency(x.rate)} = ${currency(x.total)}${x.cadence==='monthly'?'/mo':' once'} <span class="muted">(${CARD[x.cadence==='monthly'||x.category==='onboarding'?x.category:'other']})</span>`).join('<br>'):'<em>Pricing unavailable</em>';
 const scope={Included:0,Excluded:0,'Not applicable':0};d.services.forEach(s=>scope[s.status]=(scope[s.status]||0)+1);
 $('#recap').innerHTML=
  block(1,'Client',[['Company',yes(d.client)],['Contact',yes([d.contact,d.email,d.phone].filter(Boolean).join(' · '))],['Address',yes(d.address).replace(/\n/g,'<br>')],['Proposal date',yes(d.proposal_date)],['Prepared by',yes(d.prepared_by)]])+
  block(2,'Engagement',[['Billing model',BILLING[d.billing_mode]],['Counts',`${d.users} users · ${d.workstations} workstations · ${d.servers} servers · ${d.networks} networks · ${d.mobile_devices} mobile devices`],['Term',`${d.term_months} months initial · ${d.renewal_months} months renewal · ${d.notice_days} days notice`],['MSA date',d.msa_date||'<em>To be confirmed</em>'],['SOW effective',d.effective_date||'<em>To be confirmed</em>']])+
  block(3,'Discovery',[['Current state (slide)',d.current_state.trim()?d.current_state.split('\n').filter(x=>x.trim()).map(escapeHtml).join('<br>'):'<em>Workstation and server counts</em>'],...discovery])+
  block(4,'Inventory',[['Equipment',assets]])+
  block(5,'Pricing',[['Line items',billed],['Monthly',q?`${currency(q.net)} before tax (discount ${currency(q.discount)}); ${currency(q.monthly)} with ${currency(q.tax)} tax`:'—'],['Backup card label',escapeHtml(d.backup_label)],['One-time',q?currency(q.one_time):'—'],['Term total',q?currency(q.term_total):'—'],['Hourly',`${currency(d.hourly_rate)} onsite · ${currency(d.after_hours_rate)} after hours`],['Tax review',d.tax_reviewed?'Reviewed':'<strong>Not reviewed</strong>']])+
  block(6,'Scope',[['Services',`${scope.Included} included · ${scope.Excluded} excluded · ${scope['Not applicable']} not applicable`],['Exclusions',yes(d.exclusions)]]);
}

// ---------- Quote ----------
function scheduleQuote(){if($('#studio').hidden)return;clearTimeout(timer);timer=setTimeout(updateQuote,250);}
async function updateQuote(){
 const seq=++quoteSequence,data=collect();$('#summaryClient').textContent=data.client||'New client';if(!data.client)data.client='New client';if(!data.proposal_date)data.proposal_date=today();
 try{const q=await(await api('/api/quote','POST',data)).json();if(seq!==quoteSequence)return;lastQuote=q;
  $('#monthly').textContent=currency(q.monthly);$('#once').textContent=currency(q.one_time);$('#first').textContent=currency(q.first_month);$('#term').textContent=currency(q.term_total);
  $('#breakdown').innerHTML=q.lines.filter(x=>x.cadence==='monthly').map(x=>`<div class="sumrow"><span>${escapeHtml(x.description)}</span><strong>${currency(x.total)}</strong></div>`).join('')+`<div class="sumrow"><span>Discount</span><strong>−${currency(q.discount)}</strong></div><div class="sumrow"><span>Monthly tax</span><strong>${currency(q.tax)}</strong></div>`;
  $('#warnings').innerHTML=q.warnings.map(w=>`<div class="warning">${escapeHtml(w)}</div>`).join('');
  $('#summaryWarnings').textContent=q.warnings.length?`${q.warnings.length} review warning${q.warnings.length>1?'s':''} — see Review & export.`:'';
  if(step===STEPS.length&&!$('#wizard').hidden)renderRecap();
  if(step===4)renderInventoryCheck();
 }catch(e){if(seq===quoteSequence){lastQuote=null;$('#monthly').textContent='—';$('#warnings').innerHTML=`<div class="warning">${escapeHtml(e.message)}</div>`;$('#summaryWarnings').textContent=e.message;}}
}

// ---------- Saved proposals ----------
async function refreshList(){const saved=await(await api('/api/proposals')).json();$('#saved').replaceChildren();for(const p of saved){const b=document.createElement('button');b.textContent=p.client;b.title='Updated '+new Date(p.updated).toLocaleString();b.onclick=async()=>{if(!canReplace())return;try{await loadProposal(p.id);message('Draft loaded.');}catch(e){message(e.message,true);}};$('#saved').append(b);}}
function canReplace(){return !writing&&(!isDirty()||confirm('Discard unsaved changes?'));}
$('#new').onclick=()=>{if(!canReplace())return;currentId=null;currentVersion=null;fill({proposal_date:today()});refreshHistory();$('#draftState').textContent='New proposal · not saved';message('');startWizard();};
$('#example').onclick=async()=>{if(!canReplace())return;try{fill(await(await api('/api/example')).json());currentId=null;currentVersion=null;refreshHistory();dirty();markAllVisited();go(1,false);message('Reference example loaded. Walk through each step and review the open questions before exporting.');}catch(e){message(e.message,true);}};
$('#loadScope').onclick=async()=>{if($('#services').children.length&&!confirm('Replace the current scope with the reference scope?'))return;try{$('#services').replaceChildren();(await(await api('/api/services')).json()).forEach(s=>addRow('services',s));dirty();scheduleQuote();}catch(e){message(e.message,true);}};
async function loadProposal(id){
 const r=await api('/api/proposals/'+id);fill(await r.json());currentId=id;currentVersion=Number(r.headers.get('ETag'));
 $('#draftState').textContent='All changes saved · revision '+currentVersion;markAllVisited();go(STEPS.length,false);await refreshHistory();
}
$('#save').onclick=async()=>{if(writing||!validateAll())return;writing=true;$('#save').disabled=true;try{
 const r=await(await api(currentId?'/api/proposals/'+currentId:'/api/proposals',currentId?'PUT':'POST',collect(),currentVersion)).json();
 currentId=r.id;currentVersion=r.version;$('#draftState').textContent='All changes saved · revision '+r.version;message('Revision saved.');await refreshList();await refreshHistory();refreshStepStates();
 }catch(e){message(e.message,true);}finally{writing=false;$('#save').disabled=false;}};
function filenameFrom(response,fallback='TeamLogic-Proposal.zip'){const m=/filename="?([^";]+)"?/.exec(response.headers.get('Content-Disposition')||'');return m?m[1]:fallback;}
function downloadBlob(blob,name='TeamLogic-Proposal.zip'){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),30000);}
$('#generate').onclick=async()=>{if(writing||!validateAll())return;writing=true;const button=$('#generate');button.disabled=true;$('#exportState').textContent='Building and saving your documents…';try{
 const r=await api('/api/generate'+(currentId?'?proposal_id='+encodeURIComponent(currentId):''),'POST',collect(),currentVersion);
 currentId=r.headers.get('X-Proposal-Id');currentVersion=Number(r.headers.get('X-Proposal-Version'));downloadBlob(await r.blob(),filenameFrom(r));
 $('#draftState').textContent='All changes saved · revision '+currentVersion;await refreshList();await refreshHistory();
 $('#exportState').textContent='Download ready. This exact export is saved in version history.';
 }catch(e){$('#exportState').textContent=e.message;}finally{writing=false;button.disabled=false;}};
window.addEventListener('beforeunload',e=>{if(isDirty()){e.preventDefault();e.returnValue='';}});
window.wizard={go:n=>go(n,false),step:()=>step,showHistory};

fill({proposal_date:today()});
const initial=STEPS.findIndex(([id])=>'#'+id===location.hash)+1;
if(initial>1)markAllVisited();go(initial||1,false);
api('/api/me').then(r=>r.json()).then(u=>showStudio(u.username)).catch(()=>showLogin());
