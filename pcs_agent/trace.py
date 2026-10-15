"""Durable tasks and structured evidence, independent of the legacy schema."""
from pathlib import Path
import sqlite3
import json
import time
import uuid

class Store:
    def __init__(self, folder):
        self.path=Path(folder)/'task-traces.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,prompt TEXT NOT NULL,status TEXT NOT NULL,created REAL,updated REAL,result TEXT DEFAULT '',error TEXT DEFAULT '',parent TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,task TEXT,created REAL,kind TEXT,payload TEXT);
            ''')
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;return db
    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status='interrupted',error='Application stopped. Review evidence before retrying.',updated=? WHERE status IN ('running','queued')",(time.time(),))
    def create(self,prompt,parent=None,ident=None):
        ident=ident or uuid.uuid4().hex[:8];now=time.time()
        with self.connect() as db:
            db.execute('INSERT INTO tasks(id,prompt,status,created,updated,parent) VALUES(?,?,?,?,?,?)',(ident,prompt,'queued',now,now,parent))
        return ident
    def update(self,ident,**fields):
        if not fields or not set(fields)<= {'status','result','error'}:raise ValueError('Invalid task update.')
        fields['updated']=time.time()
        with self.connect() as db:
            db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),ident))
    def event(self,ident,kind,payload):
        with self.connect() as db:
            db.execute('INSERT INTO events(task,created,kind,payload) VALUES(?,?,?,?)',(ident,time.time(),kind,json.dumps(payload,ensure_ascii=False)))
    def get(self,ident):
        with self.connect() as db:
            row=db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone()
        if row is None:raise KeyError('Task not found.')
        return dict(row)
    def tasks(self,limit=100):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT ?',(limit,))]
    def events(self,ident,after=0,limit=500):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM events WHERE task=? AND seq>? ORDER BY seq LIMIT ?',(ident,after,limit)).fetchall()
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]
    def export(self):
        with self.connect() as db:
            tasks=[dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created')]
            events=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM events ORDER BY seq')]
        return {'format':'Strident support transcript v1','tasks':tasks,'events':events,
                'privacy':'Contains task text, website content, local paths and outputs. Review before sharing. No configuration or access token included.'}
