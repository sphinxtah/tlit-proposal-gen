"""Transactional revisions, exact export retention, and explicit retention controls."""
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DATA = Path(os.environ.get('DATA_DIR', 'data'))
DATA.mkdir(exist_ok=True)
DB = DATA / 'proposals.sqlite3'

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()

def stamp(now=None):
    return (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

def cutoff(years, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        earlier = now.replace(year=now.year-years)
    except ValueError:
        earlier = now.replace(year=now.year-years, day=28)
    return stamp(earlier)

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, client TEXT, payload TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, salt TEXT, hash TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY, count INTEGER, started REAL);
        CREATE TABLE IF NOT EXISTS revisions(
            id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
            version INTEGER NOT NULL, created_at TEXT NOT NULL, author TEXT NOT NULL,
            kind TEXT NOT NULL, restored_from INTEGER, payload BLOB NOT NULL,
            encoding TEXT NOT NULL DEFAULT 'json', sha256 TEXT NOT NULL,
            UNIQUE(proposal_id,version));
        CREATE INDEX IF NOT EXISTS revision_age ON revisions(created_at);
        CREATE TABLE IF NOT EXISTS exports(
            id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, author TEXT NOT NULL, template_version TEXT NOT NULL,
            app_version TEXT NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL);
        ''')
        columns={r['name'] for r in db.execute('PRAGMA table_info(proposals)')}
        if 'version' not in columns:
            db.execute('ALTER TABLE proposals ADD COLUMN version INTEGER NOT NULL DEFAULT 0')
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute('SELECT * FROM proposals WHERE version=0').fetchall():
            append_revision(db,row['id'],json.loads(row['payload']),'migration','import',created_at=row['updated'])

def append_revision(db, pid, proposal, author, kind='save', restored_from=None, created_at=None, quote=None):
    row=db.execute('SELECT version FROM proposals WHERE id=?',(pid,)).fetchone()
    version=row['version']+1
    created_at=created_at or stamp()
    envelope={'proposal':proposal,'quote':quote}
    raw=json.dumps(envelope,ensure_ascii=False,sort_keys=True,default=str).encode('utf-8')
    rid=str(uuid4())
    db.execute('INSERT INTO revisions(id,proposal_id,version,created_at,author,kind,restored_from,payload,sha256) VALUES(?,?,?,?,?,?,?,?,?)',
               (rid,pid,version,created_at,author,kind,restored_from,raw,hashlib.sha256(raw).hexdigest()))
    db.execute('UPDATE proposals SET client=?,payload=?,updated=?,version=? WHERE id=?',
               (proposal['client'],json.dumps(proposal),created_at,version,pid))
    return {'id':pid,'version':version,'revision_id':rid}

def decode_revision(row):
    raw=gzip.decompress(row['payload']) if row['encoding']=='gzip' else bytes(row['payload'])
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:
        raise ValueError('Revision integrity check failed.')
    return json.loads(raw)

def compress_history(now=None):
    """Compress immutable snapshot payloads, never delete. ZIP exports already use DEFLATE."""
    boundary=cutoff(1,now)
    count=0
    while True:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT * FROM revisions WHERE created_at<? AND encoding='json' LIMIT 100",(boundary,)).fetchall()
            if not rows:break
            for row in rows:
                decode_revision(row)  # Validate before replacing the representation.
                raw=bytes(row['payload']); packed=gzip.compress(raw,mtime=0)
                if gzip.decompress(packed)!=raw:raise ValueError('Compression integrity check failed.')
                db.execute("UPDATE revisions SET payload=?,encoding='gzip' WHERE id=?",(packed,row['id']))
                count+=1
    return count

def purge_expired(now=None):
    """Drop expired sessions and finished login-attempt windows so the tables do not grow forever."""
    now=now if now is not None else datetime.now(timezone.utc).timestamp()
    with connect() as db:
        sessions=db.execute('DELETE FROM sessions WHERE expires<=?',(now,)).rowcount
        attempts=db.execute('DELETE FROM attempts WHERE started<=?',(now-900,)).rowcount
    return sessions+attempts

def cleanup_plan(db, boundary):
    # Latest proposal activity governs whole-proposal removal. Historical revisions
    # of active proposals are independently eligible by their own save timestamp.
    proposals=[dict(r) for r in db.execute('SELECT id,version FROM proposals WHERE updated<? ORDER BY id',(boundary,))]
    revisions=[r['id'] for r in db.execute('SELECT id FROM revisions WHERE created_at<? ORDER BY id',(boundary,))]
    exports=[r['id'] for r in db.execute('SELECT e.id FROM exports e JOIN revisions r ON r.id=e.revision_id WHERE r.created_at<? ORDER BY e.id',(boundary,))]
    token=hashlib.sha256(json.dumps([boundary,proposals,revisions,exports],sort_keys=True).encode()).hexdigest()
    return {'cutoff':boundary,'proposals':len(proposals),'revisions':len(revisions),'exports':len(exports),'token':token}

def execute_cleanup(db,boundary):
    db.execute('DELETE FROM revisions WHERE created_at<?',(boundary,))
    db.execute('DELETE FROM proposals WHERE updated<?',(boundary,))
