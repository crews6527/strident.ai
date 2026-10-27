"""Loopback-only personal console; Tailscale Serve supplies private HTTPS for phones."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import json
import secrets
import threading
import shutil
from http.cookies import SimpleCookie
from .auth import Accounts
from .config import save,validate
from .provider import Ollama

EDITABLE={'image_url','workspace','store_url','model','text_model','num_ctx','num_predict','model_timeout','task_timeout','max_task_seconds','keep_alive'}
class ConsoleServer:
    def __init__(self,config,runtime,port=None):
        if not config.get('preview_key') or len(config['preview_key']) < 32:
            raise ValueError('Create a private preview key before starting the console.')
        self.config=config;self.runtime=runtime
        self.accounts=Accounts(config["data_dir"])
        self.members={}
        self.session_lock=threading.RLock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*args):pass
            def send_data(self,status,value,kind='application/json; charset=utf-8'):
                raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
                self.send_header('X-Robots-Tag','noindex, nofollow');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if getattr(self,'set_cookie',None):self.send_header('Set-Cookie',self.set_cookie)
                if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1'):
                    self.send_header('Strict-Transport-Security','max-age=31536000')
                self.end_headers();self.wfile.write(raw)
            def allowed(self):
                host=self.headers.get('Host','').split(':')[0].lower()
                if host not in owner.config['preview_hosts']:
                    self.send_data(403,{'error':'Host is not allowed. Add the exact private Tailscale hostname using Enable-Phone.cmd.'});return False
                origin=self.headers.get('Origin')
                if origin:
                    u=urlsplit(origin)
                    if u.netloc.lower()!=self.headers.get('Host','').lower() or u.scheme not in ('http','https'):
                        self.send_data(403,{'error':'Origin is not allowed.'});return False
                self.runtime=owner.runtime
                self.account=None;self.token=''
                path=urlsplit(self.path).path
                if path in ('/api/login','/api/bootstrap'):
                    return True
                if self.path.startswith('/api/'):
                    cookie=SimpleCookie()
                    try:cookie.load(self.headers.get('Cookie',''))
                    except Exception:pass
                    self.token=cookie['strident_session'].value if 'strident_session' in cookie else ''
                    self.account=owner.accounts.session(self.token)
                    # Legacy desktop key works only until the first administrator is created.
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    legacy=not owner.accounts.has_admin() and secrets.compare_digest(token,owner.config['preview_key'])
                    if not self.account and legacy:self.account={'id':'desktop','role':'admin','username':'desktop','csrf':''}
                    if not self.account:
                        self.send_data(401,{'error':'Log in to continue.'});return False
                    if self.command=='POST' and not legacy:
                        if not secrets.compare_digest(self.headers.get('X-Strident-CSRF',''),self.account['csrf']):
                            self.send_data(403,{'error':'Invalid request token.'});return False
                    if self.account['role']!='admin':
                        permitted={'/api/me','/api/logout','/api/tasks','/api/events','/api/cancel','/api/retry','/api/export','/api/delete-account','/api/change-password'}
                        if path not in permitted:
                            self.send_data(403,{'error':'Administrator access required.'});return False
                        self.runtime=owner.member_runtime(self.account['id'])
                    if self.command=='POST':owner.accounts.limit('requests:'+self.account['id'],60,60)
                return True
            def do_GET(self):
                with owner.session_lock:self.get()
            def get(self):
                try:
                    if not self.allowed():return
                    u=urlsplit(self.path);path=u.path
                    policies={'/privacy':'privacy.md','/terms':'terms.md','/accessibility':'accessibility.md'}
                    if path in policies:
                        import html
                        text=(Path(__file__).resolve().parent.parent/'docs'/policies[path]).read_text()
                        page='<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Strident policy</title><link rel="stylesheet" href="/style.css"><body><a href="/">Back to Strident</a><main><pre>'+html.escape(text)+'</pre></main></body></html>'
                        return self.send_data(200,page.encode(),'text/html; charset=utf-8')
                    files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
                    if path in files:
                        name=files[path];raw=(Path(__file__).resolve().parent.parent/'web'/name).read_bytes()
                        return self.send_data(200,raw,{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]])
                    if path=='/api/me':return self.send_data(200,self.account)
                    if path=='/api/tasks':return self.send_data(200,self.runtime.store.tasks())
                    if path=='/api/events':
                        q=parse_qs(u.query);ident=q.get('task',[''])[0];self.runtime.store.get(ident)
                        return self.send_data(200,self.runtime.store.events(ident,int(q.get('after',['0'])[0])))
                    if path=='/api/config':return self.send_data(200,{k:v for k,v in owner.config.items() if k in EDITABLE})
                    if path=='/api/models':return self.send_data(200,Ollama(owner.config).inspect())
                    if path=='/api/export':return self.send_data(200,self.runtime.store.export())
                    self.send_data(404,{'error':'Not found.'})
                except KeyError:self.send_data(404,{'error':'Task not found.'})
                except PermissionError:self.send_data(429,{'error':'Request denied or rate limit reached. Try again later.'})
                except (ValueError,TypeError):self.send_data(400,{'error':'Invalid request. Check the supplied values.'})
                except Exception:self.send_data(500,{'error':'The request failed. Check the local service and configuration.'})
            def do_POST(self):
                with owner.session_lock:self.post()
            def post(self):
                try:
                    if not self.allowed():return
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=65536:return self.send_data(413,{'error':'Request body must be 1 to 65,536 bytes.'})
                    data=json.loads(self.rfile.read(length));path=urlsplit(self.path).path
                    if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
                    if path in ('/api/login','/api/bootstrap'):
                        if self.headers.get('X-Strident-Request')!='1' or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                            return self.send_data(403,{'error':'Use the login form.'})
                        if path=='/api/bootstrap':
                            owner.accounts.limit('bootstrap',10)
                            if owner.accounts.has_admin() or not secrets.compare_digest(str(data.get('key','')),owner.config['preview_key']):
                                return self.send_data(403,{'error':'Use administrator login, or the desktop key before initial setup.'})
                            owner.accounts.create(data.get('username'),data.get('password'),'admin')
                        token,account=owner.accounts.login(data.get('username'),data.get('password'),self.client_address[0])
                        secure='; Secure' if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1') else ''
                        self.set_cookie='strident_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+secure
                        return self.send_data(200,account)
                    if path=='/api/logout':
                        owner.accounts.logout(self.token)
                        self.set_cookie='strident_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                        return self.send_data(200,{'ok':True})
                    if path=='/api/change-password':
                        owner.accounts.login(self.account['username'],data.get('current_password'),self.client_address[0])
                        owner.accounts.reset(self.account['username'],data.get('new_password'))
                        self.set_cookie='strident_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                        return self.send_data(200,{'ok':True})
                    if path=='/api/users':
                        ident=owner.accounts.create(data.get('username'),data.get('password'),'user')
                        return self.send_data(201,{'id':ident,'role':'user'})
                    if path=='/api/delete-account':
                        if self.account['role']=='admin':return self.send_data(403,{'error':'Administrator deletion requires an operator migration.'})
                        if data.get('confirmation')!='DELETE':raise ValueError('Account deletion requires confirmation.')
                        ident=self.account['id']
                        self.runtime.controller.close()
                        folder=Path(owner.config['data_dir'])/'members'/ident
                        if folder.exists():shutil.rmtree(folder)
                        owner.accounts.delete(ident);owner.members.pop(ident,None)
                        self.set_cookie='strident_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                        return self.send_data(200,{'ok':True})
                    if path=='/api/tasks':return self.send_data(202,{'id':self.runtime.submit(data.get('prompt'))})
                    if path=='/api/cancel':self.runtime.cancel(data['id']);return self.send_data(200,{'ok':True})
                    if path=='/api/retry':return self.send_data(202,{'id':self.runtime.retry(data['id'])})
                    if path=='/api/test-model':return self.send_data(202,{'id':self.runtime.submit('/testmodel')})
                    if path=='/api/config':
                        if any(t['status'] in ('queued','running') for t in self.runtime.store.tasks(1000)):raise ValueError('Wait for active tasks or cancel them before changing settings.')
                        if set(data)-EDITABLE:raise ValueError('Unsupported setting.')
                        cfg={**owner.config,**data};validate(cfg)
                        Path(cfg['workspace']).mkdir(parents=True,exist_ok=True);save(cfg)
                        owner.config.update(cfg)
                        with self.runtime.guard:self.runtime.config.update(cfg)
                        return self.send_data(200,{'ok':True})
                    self.send_data(404,{'error':'Not found.'})
                except KeyError:self.send_data(404,{'error':'Required item or task not found.'})
                except PermissionError:self.send_data(429,{'error':'Request denied or rate limit reached. Try again later.'})
                except (ValueError,TypeError):self.send_data(400,{'error':'Invalid request. Check the supplied values.'})
                except Exception:self.send_data(500,{'error':'The request failed. Check the local service and configuration.'})
        class PersonalHTTPServer(ThreadingHTTPServer):
            daemon_threads=True
            def get_request(self):
                sock,address=super().get_request();sock.settimeout(10);return sock,address
        self.httpd=PersonalHTTPServer(('127.0.0.1',int(config['preview_port']) if port is None else port),Handler)
        self.thread=threading.Thread(target=self.httpd.serve_forever,name='strident-console',daemon=True)
    @property
    def url(self):return f'http://127.0.0.1:{self.httpd.server_port}/'
    @property
    def launch_url(self):return self.url+'#key='+self.config['preview_key']
    def start(self):self.thread.start();return self
    def member_runtime(self,ident):
        if ident not in self.members:
            from .runtime import Controller
            from .storage import State
            from .preview import PreviewRuntime
            folder=Path(self.config['data_dir'])/'members'/ident
            cfg={**self.config,'data_dir':str(folder),'workspace':str(folder/'workspace'),'apps':{},'instagram_folder':'','curbsentry_bridge':'','_member_mode':True}
            self.members[ident]=PreviewRuntime(cfg,Controller(lambda e:None,storage=State(folder)))
        return self.members[ident]
    def close(self):
        self.httpd.shutdown();self.httpd.server_close();self.thread.join(2)
        for runtime in self.members.values():runtime.controller.close()
