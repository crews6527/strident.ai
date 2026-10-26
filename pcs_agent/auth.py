"""Local account authentication. No passwords or bearer sessions in browser storage."""
from contextlib import contextmanager
from pathlib import Path
import hashlib, hmac, secrets, sqlite3, time, re

class Accounts:
    def __init__(self, folder):
        self.path=Path(folder)/'accounts.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')));
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, account TEXT NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(bucket TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);''')
        self.path.chmod(0o600)
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    @staticmethod
    def password_hash(password, salt=None):
        if not isinstance(password,str) or not 15<=len(password)<=256:
            raise ValueError('Use a password between 15 and 256 characters.')
        salt=salt or secrets.token_hex(16)
        digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=3,maxmem=64*1024*1024).hex()
        return salt+':'+digest
    def create(self,username,password,role='user'):
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username):raise ValueError('Username must be 3 to 64 letters, digits, dots, underscores or hyphens.')
        if role not in ('admin','user'):raise ValueError('Invalid role.')
        digest=self.password_hash(password);ident=secrets.token_hex(16)
        with self.db() as db:
            try:db.execute('INSERT INTO accounts VALUES(?,?,?,?)',(ident,username.casefold(),digest,role))
            except sqlite3.IntegrityError:raise ValueError('Username unavailable.') from None
        return ident
    def has_admin(self):
        with self.db() as db:return bool(db.execute("SELECT 1 FROM accounts WHERE role='admin'").fetchone())
    def limit(self,bucket,maximum=10,window=900):
        bucket=hashlib.sha256(bucket.encode()).hexdigest();now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE until<?',(now,))
            row=db.execute('SELECT * FROM attempts WHERE bucket=?',(bucket,)).fetchone()
            if row and row['count']>=maximum:raise PermissionError('Too many requests. Try again later.')
            db.execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,now+window))
    def login(self,username,password,ip):
        self.limit('login-ip:'+ip,60)
        self.limit('login-name:'+str(username).casefold(),10)
        with self.db() as db:row=db.execute('SELECT * FROM accounts WHERE username=?',(str(username).casefold(),)).fetchone()
        stored=row['password'] if row else '00'*16+':'+'00'*64
        try:valid=hmac.compare_digest(self.password_hash(password,stored.split(':')[0]),stored)
        except ValueError:valid=False
        if not row or not valid:raise PermissionError('Invalid username or password.')
        return self.new_session(dict(row))
    def new_session(self,account):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),account['id'],csrf,time.time()+8*3600))
        return token,{'id':account['id'],'username':account['username'],'role':account['role'],'csrf':csrf}
    def session(self,token):
        with self.db() as db:
            row=db.execute('SELECT a.id,a.username,a.role,s.csrf FROM sessions s JOIN accounts a ON a.id=s.account WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None
    def logout(self,token):
        with self.db() as db:db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def reset(self,username,password):
        digest=self.password_hash(password)
        with self.db() as db:
            row=db.execute('SELECT id FROM accounts WHERE username=?',(username.casefold(),)).fetchone()
            if not row:raise ValueError('Account not found.')
            db.execute('UPDATE accounts SET password=? WHERE id=?',(digest,row['id']))
            db.execute('DELETE FROM sessions WHERE account=?',(row['id'],))
    def delete(self,ident):
        with self.db() as db:
            row=db.execute('SELECT role FROM accounts WHERE id=?',(ident,)).fetchone()
            if not row or row['role']=='admin':raise PermissionError('Administrator deletion requires an operator migration.')
            db.execute('DELETE FROM sessions WHERE account=?',(ident,));db.execute('DELETE FROM accounts WHERE id=?',(ident,))
