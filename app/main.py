import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
import zipfile
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.models import Proposal, quote
from app.generate import pptx_bytes, pdf_bytes, TEMPLATES, VERSION

DATA=Path(os.environ.get('DATA_DIR','data'));DATA.mkdir(exist_ok=True)
DB=DATA/'proposals.sqlite3'
def connect():
    db=sqlite3.connect(DB);db.row_factory=sqlite3.Row;return db
with connect() as db:
    db.executescript('''CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, client TEXT, payload TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, salt TEXT, hash TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, expires REAL);
    CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY, count INTEGER, started REAL);''')
app=FastAPI(title='TeamLogic IT Proposal Generator',version='0.1.0')

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
def health():return {'status':'ok'}

@app.post('/api/login')
def login(c:Credentials,request:Request,response:Response):
    if request.headers.get('x-tlit-request')!='1':raise HTTPException(403,'Request header required.')
    ip=request.client.host
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
    with connect() as db:return [dict(x) for x in db.execute('SELECT id,client,updated FROM proposals ORDER BY updated DESC')]

@app.get('/api/proposals/{pid}')
def read(pid:str,user=Depends(authenticated)):
    with connect() as db:r=db.execute('SELECT payload FROM proposals WHERE id=?',(pid,)).fetchone()
    if not r:raise HTTPException(404,'Proposal not found.')
    return json.loads(r['payload'])

@app.post('/api/proposals')
def create(p:Proposal,user=Depends(authenticated)):
    pid=str(uuid4());return save(pid,p,user)

@app.put('/api/proposals/{pid}')
def save(pid:str,p:Proposal,user=Depends(authenticated)):
    pricing(p,user)
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO proposals VALUES(?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))",(pid,p.client,p.model_dump_json()))
    return {'id':pid}

@app.post('/api/generate')
def generate(p:Proposal,user=Depends(authenticated)):
    q=pricing(p,user)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('Proposal.pptx',pptx_bytes(p,q))
        z.writestr('Managed-IT-Services.pdf',pdf_bytes(p,q))
        z.writestr('proposal-data.json',p.model_dump_json(indent=2))
        z.writestr('generation-manifest.json',json.dumps({'template_version':VERSION,'generated_by':user,'warnings':q['warnings'],'monthly':str(q['monthly'])},indent=2))
    output.seek(0)
    return StreamingResponse(output,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="TeamLogic-Proposal.zip"'})

app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
@app.get('/')
def index():return FileResponse(Path(__file__).parent/'static/index.html')
