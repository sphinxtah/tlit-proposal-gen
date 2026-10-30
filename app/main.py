import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
import zipfile
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from app.models import Proposal, quote
from app.generate import pptx_bytes, docx_bytes, TEMPLATES, VERSION
from app.version import APP_VERSION
from app.storage import (connect, initialize, append_revision, decode_revision,
                         compress_history, cutoff, cleanup_plan, execute_cleanup, stamp, purge_expired)

initialize()

async def maintenance():
    while True:
        try:await asyncio.to_thread(compress_history)
        except Exception:logging.exception('History compression failed; original records retained')
        try:await asyncio.to_thread(purge_expired)
        except Exception:logging.exception('Session purge failed')
        await asyncio.sleep(24*3600)

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(maintenance())
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass

app=FastAPI(title='TeamLogic IT Proposal Generator',version=APP_VERSION,lifespan=lifespan)

SECURITY_HEADERS={
    'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','Cache-Control':'no-store'}

@app.middleware('http')
async def security_headers(request:Request,call_next):
    response=await call_next(request)
    for k,v in SECURITY_HEADERS.items():
        if k=='Cache-Control' and request.url.path.startswith('/static/'):continue
        response.headers.setdefault(k,v)
    return response

def client_ip(request:Request):
    """Rate-limit key. Behind Docker's port proxy or an HTTPS reverse proxy every visitor shares one
    source address, so the first header hop is honored only when the operator opts in."""
    if os.environ.get('TRUST_PROXY')=='true':
        forwarded=request.headers.get('x-forwarded-for','')
        if forwarded:return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'

def document_names(client):
    """ZIP entry names follow the reference files: ProjectCenter_IT_Proposal.pptx and
    'TeamLogicIT - Managed IT Services-ProjectCenter.docx'."""
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]+','',client).strip(' .')[:80] or 'Client'
    return f'{name}_IT_Proposal.pptx',f'TeamLogicIT - Managed IT Services-{name}.docx'

def attachment(client,version):
    slug=re.sub(r'[^A-Za-z0-9]+','-',client).strip('-')[:40] or 'Proposal'
    return {'Content-Disposition':f'attachment; filename="TeamLogic-Proposal-{slug}-r{version}.zip"'}

def authenticated(request:Request):
    token=request.cookies.get('tlit_session','')
    with connect() as db:
        session=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    if not session:raise HTTPException(401,'Please sign in.')
    if request.method not in ('GET','HEAD') and request.headers.get('x-tlit-request')!='1':
        raise HTTPException(403,'Request header required.')
    return session['username']

class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=200)

@app.get('/api/health')
def health():return {'status':'ok','version':APP_VERSION}

@app.post('/api/login')
def login(c:Credentials,request:Request,response:Response):
    if request.headers.get('x-tlit-request')!='1':raise HTTPException(403,'Request header required.')
    ip=client_ip(request)
    with connect() as db:
        attempt=db.execute('SELECT * FROM attempts WHERE ip=?',(ip,)).fetchone()
        if attempt and attempt['count']>=10 and time.time()-attempt['started']<900:
            raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
        user=db.execute('SELECT * FROM users WHERE username=?',(c.username,)).fetchone()
        salt=user['salt'] if user else '0'*32
        digest=hashlib.scrypt(c.password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        if not user or not hmac.compare_digest(digest,user['hash']):
            count=attempt['count']+1 if attempt and time.time()-attempt['started']<900 else 1
            started=attempt['started'] if count>1 else time.time()
            db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(ip,count,started));db.commit()
            raise HTTPException(401,'Incorrect username or password.')
        db.execute('DELETE FROM attempts WHERE ip=?',(ip,))
        token=secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),c.username,time.time()+8*3600))
    response.set_cookie('tlit_session',token,httponly=True,samesite='strict',secure=os.environ.get('COOKIE_SECURE')=='true',max_age=8*3600)
    return {'username':c.username}

@app.post('/api/logout')
def logout(request:Request,response:Response,user=Depends(authenticated)):
    with connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies['tlit_session'].encode()).hexdigest(),))
    response.delete_cookie('tlit_session');return {'ok':True}

@app.get('/api/me')
def me(user=Depends(authenticated)):return {'username':user}

@app.get('/api/example')
def example(user=Depends(authenticated)):
    local=TEMPLATES/'example.private.json'
    return json.loads((local if local.exists() else TEMPLATES/'example.json').read_text(encoding='utf-8'))

@app.get('/api/services')
def services(user=Depends(authenticated)):return json.loads((TEMPLATES/'services.json').read_text(encoding='utf-8'))

@app.post('/api/quote')
def pricing(p:Proposal,user=Depends(authenticated)):
    try:return quote(p)
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/api/proposals')
def listing(user=Depends(authenticated)):
    with connect() as db:return [dict(x) for x in db.execute('SELECT id,client,updated,version FROM proposals ORDER BY updated DESC')]

@app.get('/api/proposals/{pid}')
def read(pid:str,response:Response,user=Depends(authenticated)):
    with connect() as db:r=db.execute('SELECT payload,version FROM proposals WHERE id=?',(pid,)).fetchone()
    if not r:raise HTTPException(404,'Proposal not found.')
    response.headers['ETag']=str(r['version'])
    return json.loads(r['payload'])

def check_version(db,pid,expected):
    row=db.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone()
    if not row:raise HTTPException(404,'Proposal not found.')
    if expected is None:raise HTTPException(428,'Reload the proposal before changing it.')
    if str(row['version'])!=expected.strip().strip('"'):raise HTTPException(409,'This proposal changed in another session. Reload it before saving.')
    return row

@app.post('/api/proposals')
def create(p:Proposal,user=Depends(authenticated)):
    q=pricing(p,user);pid=str(uuid4())
    with connect() as db:
        db.execute('INSERT INTO proposals(id,version) VALUES(?,0)',(pid,))
        return append_revision(db,pid,p.model_dump(mode='json'),user,quote=q)

@app.put('/api/proposals/{pid}')
def save(pid:str,p:Proposal,user=Depends(authenticated),if_match:str|None=Header(default=None)):
    q=pricing(p,user)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');check_version(db,pid,if_match)
        return append_revision(db,pid,p.model_dump(mode='json'),user,quote=q)

@app.get('/api/proposals/{pid}/history')
def history(pid:str,user=Depends(authenticated)):
    with connect() as db:
        if not db.execute('SELECT 1 FROM proposals WHERE id=?',(pid,)).fetchone():raise HTTPException(404,'Proposal not found.')
        rows=[dict(r) for r in db.execute('SELECT id,version,created_at,author,kind,restored_from,encoding FROM revisions WHERE proposal_id=? ORDER BY version DESC',(pid,))]
        for row in rows:
            row['exports']=[dict(e) for e in db.execute('SELECT id,created_at,author,app_version,template_version FROM exports WHERE revision_id=? ORDER BY created_at DESC',(row['id'],))]
        return rows

def revision(db,pid,rid):
    row=db.execute('SELECT * FROM revisions WHERE proposal_id=? AND id=?',(pid,rid)).fetchone()
    if not row:raise HTTPException(404,'Revision not found.')
    return row

@app.get('/api/proposals/{pid}/history/{rid}')
def read_revision(pid:str,rid:str,user=Depends(authenticated)):
    with connect() as db:return decode_revision(revision(db,pid,rid))

@app.post('/api/proposals/{pid}/history/{rid}/restore')
def restore(pid:str,rid:str,user=Depends(authenticated),if_match:str|None=Header(default=None)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');check_version(db,pid,if_match)
        old=revision(db,pid,rid)
        try:snapshot=decode_revision(old)
        except ValueError as e:raise HTTPException(500,str(e))
        try:p=Proposal(**snapshot['proposal'])
        except ValidationError as e:
            raise HTTPException(422,'This revision was saved with an older data layout and cannot be restored automatically: '+'; '.join(f"{'.'.join(map(str,x['loc']))}: {x['msg']}" for x in e.errors()))
        q=pricing(p,user)
        return append_revision(db,pid,p.model_dump(mode='json'),user,'restore',restored_from=old['version'],quote=q)

@app.get('/api/exports/{eid}')
def download_export(eid:str,user=Depends(authenticated)):
    with connect() as db:row=db.execute('SELECT e.payload,e.sha256,p.client,r.version FROM exports e JOIN revisions r ON r.id=e.revision_id JOIN proposals p ON p.id=r.proposal_id WHERE e.id=?',(eid,)).fetchone()
    if not row:raise HTTPException(404,'Export not found.')
    if hashlib.sha256(row['payload']).hexdigest()!=row['sha256']:raise HTTPException(500,'Export integrity check failed.')
    return Response(row['payload'],media_type='application/zip',headers=attachment(row['client'],row['version']))

class Confirmation(BaseModel):
    confirmation:str

@app.delete('/api/proposals/{pid}')
def delete_proposal(pid:str,c:Confirmation,user=Depends(authenticated),if_match:str|None=Header(default=None)):
    if c.confirmation!='DELETE':raise HTTPException(422,'Type DELETE to confirm.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');check_version(db,pid,if_match)
        db.execute('DELETE FROM proposals WHERE id=?',(pid,))
    return {'deleted':True}

@app.delete('/api/proposals/{pid}/history/{rid}')
def delete_revision(pid:str,rid:str,c:Confirmation,user=Depends(authenticated),if_match:str|None=Header(default=None)):
    if c.confirmation!='DELETE':raise HTTPException(422,'Type DELETE to confirm.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');current=check_version(db,pid,if_match);old=revision(db,pid,rid)
        if old['version']==current['version']:raise HTTPException(409,'The current revision cannot be removed alone. Delete the whole proposal instead.')
        db.execute('DELETE FROM revisions WHERE id=?',(rid,))
    return {'deleted':True}

class CleanupConfirmation(Confirmation):
    cutoff:str
    token:str

@app.get('/api/retention/preview')
def preview_cleanup(user=Depends(authenticated)):
    with connect() as db:return cleanup_plan(db,cutoff(2))

@app.post('/api/retention/delete')
def delete_old(c:CleanupConfirmation,user=Depends(authenticated)):
    if c.confirmation!='DELETE OLD HISTORY':raise HTTPException(422,'Type DELETE OLD HISTORY to confirm.')
    # Accept only the exact older boundary previewed by the user, never newer records.
    from datetime import datetime, timezone
    try:boundary=datetime.fromisoformat(c.cutoff.replace('Z','+00:00'))
    except ValueError:raise HTTPException(422,'Invalid cutoff.')
    if boundary.tzinfo is None or boundary>datetime.fromisoformat(cutoff(2).replace('Z','+00:00')):raise HTTPException(422,'Cutoff must be at least two years ago.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');plan=cleanup_plan(db,c.cutoff)
        if not hmac.compare_digest(plan['token'],c.token):raise HTTPException(409,'Records changed. Preview cleanup again.')
        execute_cleanup(db,c.cutoff)
    return plan

@app.post('/api/generate')
def generate(p:Proposal,response:Response,user=Depends(authenticated),proposal_id:str|None=None,if_match:str|None=Header(default=None)):
    q=pricing(p,user)
    ppt=pptx_bytes(p,q);agreement=docx_bytes(p,q);deck_name,agreement_name=document_names(p.client)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if proposal_id:check_version(db,proposal_id,if_match)
        else:
            proposal_id=str(uuid4());db.execute('INSERT INTO proposals(id,version) VALUES(?,0)',(proposal_id,))
        saved=append_revision(db,proposal_id,p.model_dump(mode='json'),user,'export',quote=q)
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr(deck_name,ppt);z.writestr(agreement_name,agreement)
            z.writestr('proposal-data.json',p.model_dump_json(indent=2))
            z.writestr('generation-manifest.json',json.dumps({'app_version':APP_VERSION,'template_version':VERSION,'generated_by':user,'generated_at':stamp(),**saved,'warnings':q['warnings'],'monthly':str(q['monthly'])},indent=2))
        raw=output.getvalue()
        db.execute('INSERT INTO exports VALUES(?,?,?,?,?,?,?,?)',(str(uuid4()),saved['revision_id'],stamp(),user,VERSION,APP_VERSION,raw,hashlib.sha256(raw).hexdigest()))
    return Response(raw,media_type='application/zip',headers={**attachment(p.client,saved['version']),'X-Proposal-Id':proposal_id,'X-Proposal-Version':str(saved['version'])})

app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
@app.get('/')
def index():return FileResponse(Path(__file__).parent/'static/index.html')
