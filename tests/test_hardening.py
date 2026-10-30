"""Regression tests for fixes made alongside the wizard UI: headers, rate-limit keys, legacy restores, filenames."""
import hashlib
import json
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app, authenticated
from app import storage
from app.models import Proposal
from app.generate import TEMPLATES

PASSWORD='hardening-test-password'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'hardening.sqlite3')
    storage.initialize()
    salt=b'fedcba9876543210'
    with storage.connect() as db:
        db.execute('INSERT INTO users VALUES(?,?,?)',('h-user',salt.hex(),hashlib.scrypt(PASSWORD.encode(),salt=salt,n=16384,r=8,p=1).hex()))
    with TestClient(app,headers={'X-TLIT-Request':'1'}) as c:yield c
    app.dependency_overrides.clear()

def data():return Proposal(**json.loads((TEMPLATES/'example.json').read_text())).model_dump(mode='json')

def test_security_headers_present(client):
    for path in ['/','/api/health','/static/app.js']:
        r=client.get(path);assert r.status_code==200
        assert r.headers['X-Content-Type-Options']=='nosniff'
        assert "script-src 'self'" in r.headers['Content-Security-Policy']
        assert r.headers['X-Frame-Options']=='DENY'
    assert client.get('/api/health').headers['Cache-Control']=='no-store'
    assert 'no-store' not in client.get('/static/app.js').headers.get('Cache-Control','')

def test_forwarded_header_ignored_unless_trusted(client,monkeypatch):
    bad={'username':'h-user','password':'wrong'}
    for i in range(10):
        assert client.post('/api/login',json=bad,headers={'X-Forwarded-For':f'10.0.0.{i}'}).status_code==401
    # Default: every visitor shares the socket address, so the limit is shared too.
    assert client.post('/api/login',json=bad,headers={'X-Forwarded-For':'10.0.0.99'}).status_code==429
    monkeypatch.setenv('TRUST_PROXY','true')
    assert client.post('/api/login',json=bad,headers={'X-Forwarded-For':'10.0.0.99'}).status_code==401
    assert client.post('/api/login',json={'username':'h-user','password':PASSWORD},headers={'X-Forwarded-For':'10.0.0.99'}).status_code==200

def test_export_filename_uses_client_and_revision(client):
    assert client.post('/api/login',json={'username':'h-user','password':PASSWORD}).status_code==200
    p=data();p['client']='Acme & Sons, LLC / West'
    r=client.post('/api/generate',json=p);assert r.status_code==200
    assert r.headers['Content-Disposition']=='attachment; filename="TeamLogic-Proposal-Acme-Sons-LLC-West-r1.zip"'
    pid=r.headers['X-Proposal-Id']
    eid=client.get(f'/api/proposals/{pid}/history').json()[0]['exports'][0]['id']
    assert client.get('/api/exports/'+eid).headers['Content-Disposition'].endswith('-r1.zip"')

def test_quoted_etag_accepted(client):
    app.dependency_overrides[authenticated]=lambda:'h-user'
    p=data();pid=client.post('/api/proposals',json=p).json()['id']
    assert client.put('/api/proposals/'+pid,json=p,headers={'If-Match':'"1"'}).status_code==200

def test_restore_of_legacy_layout_is_a_clean_422(client):
    app.dependency_overrides[authenticated]=lambda:'h-user'
    p=data();first=client.post('/api/proposals',json=p).json();pid=first['id']
    legacy=json.dumps({'proposal':{**p,'retired_field':'x'},'quote':None},sort_keys=True).encode()
    with storage.connect() as db:
        db.execute('UPDATE revisions SET payload=?,sha256=? WHERE id=?',(legacy,hashlib.sha256(legacy).hexdigest(),first['revision_id']))
    client.put('/api/proposals/'+pid,json=p,headers={'If-Match':'1'})
    r=client.post(f'/api/proposals/{pid}/history/{first["revision_id"]}/restore',headers={'If-Match':'2'})
    assert r.status_code==422 and 'retired_field' in r.json()['detail']
    assert client.get('/api/proposals/'+pid+'/history').json()[0]['version']==2

def test_purge_expired_sessions_and_attempts(client):
    with storage.connect() as db:
        db.execute('INSERT INTO sessions VALUES(?,?,?)',('old','h-user',time.time()-1))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',('live','h-user',time.time()+3600))
        db.execute('INSERT INTO attempts VALUES(?,?,?)',('1.1.1.1',3,time.time()-1000))
        db.execute('INSERT INTO attempts VALUES(?,?,?)',('2.2.2.2',3,time.time()-10))
    assert storage.purge_expired()==2
    with storage.connect() as db:
        assert [r['token'] for r in db.execute('SELECT token FROM sessions')]==['live']
        assert [r['ip'] for r in db.execute('SELECT ip FROM attempts')]==['2.2.2.2']

def test_index_declares_wizard_steps(client):
    html=client.get('/').text
    assert html.count('class="step"')==7 and 'id="stepper"' in html and 'name="billing_mode"' in html
