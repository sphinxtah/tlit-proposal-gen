from datetime import datetime, timezone
import hashlib
import io
import json
import sqlite3
import zipfile
import pytest
from fastapi.testclient import TestClient
from app.main import app, authenticated
from app import storage
from app.models import Proposal
from app.generate import TEMPLATES

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'history.sqlite3')
    storage.initialize()
    app.dependency_overrides[authenticated]=lambda:'history-tester'
    with TestClient(app) as c:yield c
    app.dependency_overrides.clear()

def data():return Proposal(**json.loads((TEMPLATES/'example.json').read_text())).model_dump(mode='json')

def test_history_restoration_conflicts_and_exact_export(client):
    p=data();first=client.post('/api/proposals',json=p).json();pid=first['id']
    p['workstation_rate']='99'
    assert client.put('/api/proposals/'+pid,json=p).status_code==428
    second=client.put('/api/proposals/'+pid,json=p,headers={'If-Match':'1'});assert second.status_code==200
    assert client.put('/api/proposals/'+pid,json=p,headers={'If-Match':'1'}).status_code==409
    h=client.get('/api/proposals/'+pid+'/history').json();assert len(h)==2
    old=client.get(f'/api/proposals/{pid}/history/{first["revision_id"]}').json()
    assert old['proposal']['workstation_rate']=='80' and old['quote']['monthly']=='410.00'
    restored=client.post(f'/api/proposals/{pid}/history/{first["revision_id"]}/restore',headers={'If-Match':'2'})
    assert restored.json()['version']==3
    p=client.get('/api/proposals/'+pid).json();assert p['workstation_rate']=='80'
    output=client.post('/api/generate?proposal_id='+pid,json=p,headers={'If-Match':'3'})
    assert output.status_code==200 and output.headers['X-Proposal-Version']=='4'
    hist=client.get('/api/proposals/'+pid+'/history').json();eid=hist[0]['exports'][0]['id']
    assert client.get('/api/exports/'+eid).content==output.content
    manifest=json.loads(zipfile.ZipFile(io.BytesIO(output.content)).read('generation-manifest.json'))
    assert manifest['app_version']=='0.1.0' and manifest['version']==4
    with storage.connect() as db:
        db.execute("UPDATE revisions SET created_at='2020-01-01T00:00:00.000000Z' WHERE proposal_id=?",(pid,))
    assert storage.compress_history()==4
    assert storage.compress_history()==0
    assert client.get(f'/api/proposals/{pid}/history/{first["revision_id"]}').json()==old
    assert client.get('/api/exports/'+eid).content==output.content
    assert client.post(f'/api/proposals/{pid}/history/{first["revision_id"]}/restore',headers={'If-Match':'4'}).json()['version']==5

def test_individual_and_bulk_deletion(client):
    p=data();a=client.post('/api/proposals',json=p).json();pid=a['id']
    current_path=f'/api/proposals/{pid}/history/{a["revision_id"]}'
    assert client.request('DELETE',current_path,json={'confirmation':'DELETE'},headers={'If-Match':'1'}).status_code==409
    exp=client.post('/api/generate?proposal_id='+pid,json=p,headers={'If-Match':'1'});assert exp.status_code==200
    with storage.connect() as db:
        db.execute("UPDATE revisions SET created_at='2020-01-01T00:00:00.000000Z' WHERE proposal_id=?",(pid,))
        db.execute("UPDATE proposals SET updated='2020-01-01T00:00:00.000000Z' WHERE id=?",(pid,))
    b=client.post('/api/proposals',json=p).json()
    # An old revision of an active proposal is eligible, but its current revision survives.
    with storage.connect() as db:db.execute("UPDATE revisions SET created_at='2020-01-01T00:00:00.000000Z' WHERE id=?",(b['revision_id'],))
    client.put('/api/proposals/'+b['id'],json=p,headers={'If-Match':'1'})
    plan=client.get('/api/retention/preview').json()
    assert (plan['proposals'],plan['revisions'],plan['exports'])==(1,3,1)
    body={k:plan[k] for k in ['cutoff','token']}
    assert client.post('/api/retention/delete',json={**body,'confirmation':'wrong'}).status_code==422
    assert client.post('/api/retention/delete',json={**body,'confirmation':'DELETE OLD HISTORY','token':'stale'}).status_code==409
    assert client.post('/api/retention/delete',json={**body,'confirmation':'DELETE OLD HISTORY'}).status_code==200
    assert client.get('/api/proposals/'+pid).status_code==404
    assert len(client.get('/api/proposals/'+b['id']+'/history').json())==1
    client.put('/api/proposals/'+b['id'],json=p,headers={'If-Match':'2'})
    hist=client.get('/api/proposals/'+b['id']+'/history').json()
    assert client.request('DELETE',f'/api/proposals/{b["id"]}/history/{hist[1]["id"]}',json={'confirmation':'DELETE'},headers={'If-Match':'3'}).status_code==200
    assert client.request('DELETE','/api/proposals/'+b['id'],json={'confirmation':'DELETE'},headers={'If-Match':'3'}).status_code==200
    with storage.connect() as db:assert db.execute('SELECT COUNT(*) FROM exports').fetchone()[0]==0

def test_migration_preserves_legacy_draft(tmp_path,monkeypatch):
    path=tmp_path/'legacy.sqlite3';monkeypatch.setattr(storage,'DB',path)
    p=data()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE proposals(id TEXT PRIMARY KEY,client TEXT,payload TEXT,updated TEXT)')
        db.execute('INSERT INTO proposals VALUES(?,?,?,?)',('legacy',p['client'],json.dumps(p),'2024-01-01T00:00:00Z'))
    storage.initialize();storage.initialize()
    with storage.connect() as db:
        rows=db.execute('SELECT * FROM revisions').fetchall();assert len(rows)==1
        assert storage.decode_revision(rows[0])['proposal']==p
        assert rows[0]['author']=='migration'

def test_calendar_cutoff_and_compression_boundary(client):
    now=datetime(2028,2,29,12,tzinfo=timezone.utc)
    assert storage.cutoff(1,now)=='2027-02-28T12:00:00.000000Z'
    a=client.post('/api/proposals',json=data()).json()
    with storage.connect() as db:db.execute('UPDATE revisions SET created_at=? WHERE id=?',(storage.cutoff(1,now),a['revision_id']))
    assert storage.compress_history(now)==0

def test_stale_cleanup_preview_rejected_after_restore(client):
    a=client.post('/api/proposals',json=data()).json();pid=a['id']
    with storage.connect() as db:
        db.execute("UPDATE revisions SET created_at='2020-01-01T00:00:00.000000Z' WHERE proposal_id=?",(pid,))
        db.execute("UPDATE proposals SET updated='2020-01-01T00:00:00.000000Z' WHERE id=?",(pid,))
    plan=client.get('/api/retention/preview').json()
    client.post(f'/api/proposals/{pid}/history/{a["revision_id"]}/restore',headers={'If-Match':'1'})
    body={k:plan[k] for k in ['cutoff','token']}
    assert client.post('/api/retention/delete',json={**body,'confirmation':'DELETE OLD HISTORY'}).status_code==409
    assert client.get('/api/proposals/'+pid).status_code==200
