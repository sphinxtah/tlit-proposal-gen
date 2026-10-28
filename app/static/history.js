// Loaded after app.js; shares the active proposal state.
document.querySelector('main').insertAdjacentHTML('beforeend',`
<section id="history"><div class="section-title"><span>07</span><div><h2>Version history</h2><p>Every save and export is retained until you choose to delete it.</p></div></div>
<p class="muted">History older than one year is compressed automatically. Restore creates a new revision; previous versions stay available.</p>
<button id="reloadCurrent" class="secondary">Reload current revision</button>
<div id="historyRows">Save a proposal to start its history.</div>
<button id="deleteProposal" class="danger" hidden>Delete this proposal and all history</button>
<details><summary>Storage cleanup</summary><p>Preview and permanently delete history older than two years. Proposals with no activity for two years are removed entirely. Recent proposals and their recent revisions remain.</p>
<button id="cleanupPreview" class="danger">Preview records older than two years</button></details>
</section>
<dialog id="historyDialog"><h2 id="historyDialogTitle"></h2><pre id="historyDetail"></pre><button id="closeHistory">Close</button></dialog>`);
document.querySelector('nav').insertAdjacentHTML('beforeend','<a href="#history">07 &nbsp; Version history</a>');
const releaseLabel=document.createElement('p');releaseLabel.className='summary-note';document.querySelector('.aside-bottom').after(releaseLabel);
fetch('/api/health').then(r=>r.json()).then(x=>{releaseLabel.textContent='Proposal Studio v'+x.version;});
$('#closeHistory').onclick=()=>$('#historyDialog').close();
$('#reloadCurrent').onclick=async()=>{if(currentId&&canReplace())try{await loadProposal(currentId);message('Current revision loaded.');}catch(e){message(e.message,true);}};
async function refreshHistory(){
 const container=$('#historyRows');if(!container)return;
 $('#deleteProposal').hidden=!currentId;$('#reloadCurrent').disabled=!currentId;
 if(!currentId){container.textContent='Save a proposal to start its history.';return;}
 const pid=currentId;const history=await(await api('/api/proposals/'+pid+'/history')).json();if(pid!==currentId)return;
 container.replaceChildren();
 for(const item of history){
  const row=document.createElement('article');row.className='history-row';
  const label=document.createElement('p');label.textContent=`Revision ${item.version}${item.version===currentVersion?' (current)':''} · ${item.kind}${item.restored_from?' from revision '+item.restored_from:''} · ${item.author} · ${new Date(item.created_at).toLocaleString()}${item.encoding==='gzip'?' · compressed':''}`;row.append(label);
  const action=(title,fn,danger=false)=>{const b=document.createElement('button');b.type='button';b.textContent=title;b.className=danger?'danger':'secondary';b.onclick=async()=>{if(writing)return;b.disabled=true;try{await fn();}catch(e){message(e.message,true);}finally{b.disabled=false;}};row.append(b);};
  const path='/api/proposals/'+pid+'/history/'+item.id;
  action('View snapshot',async()=>{const detail=await(await api(path)).json();$('#historyDialogTitle').textContent='Revision '+item.version;$('#historyDetail').textContent=JSON.stringify(detail,null,2);$('#historyDialog').showModal();});
  if(item.version!==currentVersion){
   action('Restore as new revision',async()=>{if(!canReplace()||!confirm('Restore revision '+item.version+' as a new current revision? Existing history will remain.'))return;await api(path+'/restore','POST',undefined,currentVersion);await loadProposal(pid);await refreshList();message('Historical revision restored as a new revision.');});
   action('Delete revision',async()=>{if(prompt('Permanently delete revision '+item.version+' and its exported files? Type DELETE to confirm.')!=='DELETE')return;await api(path,'DELETE',{confirmation:'DELETE'},currentVersion);await refreshHistory();message('Revision and its exports deleted.');},true);
  }
  for(const exported of item.exports)action('Download saved export',async()=>downloadBlob(await(await api('/api/exports/'+exported.id)).blob()));
  container.append(row);
 }
}
$('#deleteProposal').onclick=async()=>{
 if(writing||!currentId||prompt('Permanently delete this entire proposal, every revision and every saved export? Type DELETE to confirm.')!=='DELETE')return;
 try{await api('/api/proposals/'+currentId,'DELETE',{confirmation:'DELETE'},currentVersion);resetDeleted();await refreshList();message('Proposal and all history deleted.');}catch(e){message(e.message,true);}
};
function resetDeleted(){currentId=null;currentVersion=null;fill({proposal_date:today()});$('#draftState').textContent='New proposal · not saved';refreshHistory();}
$('#cleanupPreview').onclick=async()=>{
 if(writing)return;
 try{
  const preview=await(await api('/api/retention/preview')).json();
  if(!preview.revisions&&!preview.proposals){message('No history older than two years.');return;}
  const warning=`Before ${new Date(preview.cutoff).toLocaleString()}: permanently delete ${preview.revisions} revisions and ${preview.exports} exports, including ${preview.proposals} inactive proposals. This cannot be undone in the app. Type DELETE OLD HISTORY to confirm.`;
  if(prompt(warning)!=='DELETE OLD HISTORY')return;
  await api('/api/retention/delete','POST',{confirmation:'DELETE OLD HISTORY',cutoff:preview.cutoff,token:preview.token});
  const remaining=await(await api('/api/proposals')).json();
  if(currentId&&!remaining.some(p=>p.id===currentId))resetDeleted();else await refreshHistory();
  await refreshList();message('Old history deleted. Backups are managed separately.');
 }catch(e){message(e.message,true);}
};
