"""Loopback-only personal console; Tailscale Serve supplies private HTTPS for phones."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import json
import secrets
import threading
from .config import save,validate
from .provider import Ollama

EDITABLE={'workspace','store_url','model','text_model','num_ctx','num_predict','model_timeout','task_timeout','max_task_seconds','keep_alive'}
class ConsoleServer:
    def __init__(self,config,runtime,port=None):
        if not config.get('preview_key') or len(config['preview_key']) < 32:
            raise ValueError('Create a private preview key before starting the console.')
        self.config=config;self.runtime=runtime
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*args):pass
            def send_data(self,status,value,kind='application/json; charset=utf-8'):
                raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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
                if self.path.startswith('/api/'):
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    if not secrets.compare_digest(token,owner.config['preview_key']):
                        self.send_data(401,{'error':'Paste the console access key shown on the desktop.'});return False
                return True
            def do_GET(self):
                try:
                    if not self.allowed():return
                    u=urlsplit(self.path);path=u.path
                    files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
                    if path in files:
                        name=files[path];raw=(Path(__file__).resolve().parent.parent/'web'/name).read_bytes()
                        return self.send_data(200,raw,{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]])
                    if path=='/api/tasks':return self.send_data(200,owner.runtime.store.tasks())
                    if path=='/api/events':
                        q=parse_qs(u.query);ident=q.get('task',[''])[0];owner.runtime.store.get(ident)
                        return self.send_data(200,owner.runtime.store.events(ident,int(q.get('after',['0'])[0])))
                    if path=='/api/config':return self.send_data(200,{k:v for k,v in owner.config.items() if k in EDITABLE})
                    if path=='/api/models':return self.send_data(200,Ollama(owner.config).inspect())
                    if path=='/api/export':return self.send_data(200,owner.runtime.store.export())
                    self.send_data(404,{'error':'Not found.'})
                except KeyError:self.send_data(404,{'error':'Task not found.'})
                except Exception as exc:self.send_data(400,{'error':str(exc)})
            def do_POST(self):
                try:
                    if not self.allowed():return
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=65536:return self.send_data(413,{'error':'Request body must be 1 to 65,536 bytes.'})
                    data=json.loads(self.rfile.read(length));path=urlsplit(self.path).path
                    if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
                    if path=='/api/tasks':return self.send_data(202,{'id':owner.runtime.submit(data.get('prompt'))})
                    if path=='/api/cancel':owner.runtime.cancel(data['id']);return self.send_data(200,{'ok':True})
                    if path=='/api/retry':return self.send_data(202,{'id':owner.runtime.retry(data['id'])})
                    if path=='/api/test-model':return self.send_data(202,{'id':owner.runtime.submit('/testmodel')})
                    if path=='/api/config':
                        if any(t['status'] in ('queued','running') for t in owner.runtime.store.tasks(1000)):raise ValueError('Wait for active tasks or cancel them before changing settings.')
                        if set(data)-EDITABLE:raise ValueError('Unsupported setting.')
                        cfg={**owner.config,**data};validate(cfg)
                        Path(cfg['workspace']).mkdir(parents=True,exist_ok=True);save(cfg)
                        owner.config.update(cfg)
                        with owner.runtime.guard:owner.runtime.config.update(cfg)
                        return self.send_data(200,{'ok':True})
                    self.send_data(404,{'error':'Not found.'})
                except KeyError:self.send_data(404,{'error':'Required item or task not found.'})
                except Exception as exc:self.send_data(400,{'error':str(exc)})
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
    def close(self):self.httpd.shutdown();self.httpd.server_close();self.thread.join(2)
