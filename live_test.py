"""Real local agent in an isolated data folder; uses the operator's installed Ollama."""
import argparse,multiprocessing,threading,signal,secrets,webbrowser
from pathlib import Path
from pcs_agent.config import load,validate
from pcs_agent.instance import InstanceLock
from pcs_agent.runtime import Controller
from pcs_agent.storage import State
from pcs_agent.server import ConsoleServer
from pcs_agent.preview import PreviewRuntime

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model');parser.add_argument('--port',type=int,default=0);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    current=load();folder=Path(__file__).resolve().parent/'.live-test';folder.mkdir(mode=0o700,exist_ok=True)
    cfg=validate({**current,'data_dir':str(folder/'data'),'workspace':str(folder/'workspace'),'apps':{},'instagram_folder':'','curbsentry_bridge':'','preview_hosts':['127.0.0.1','localhost'],'preview_key':secrets.token_urlsafe(32)})
    if args.model:cfg['model']=args.model;cfg['text_model']=args.model
    Path(cfg['workspace']).mkdir(exist_ok=True)
    lock=InstanceLock(cfg['data_dir'])
    controller=Controller(lambda e:None,storage=State(cfg['data_dir']))
    server=ConsoleServer(cfg,PreviewRuntime(cfg,controller),args.port).start()
    stop=threading.Event()
    signal.signal(signal.SIGINT,lambda *_:stop.set());signal.signal(signal.SIGTERM,lambda *_:stop.set())
    print('Isolated live test: '+server.url,flush=True)
    if not server.accounts.has_admin():print('Initial setup key: '+cfg['preview_key'],flush=True)
    print('Model: '+(cfg['model'] or 'not configured; select an installed model in administrator Settings'),flush=True)
    if not args.no_browser:webbrowser.open(server.launch_url,new=2)
    try:stop.wait()
    finally:server.close();controller.close();lock.close()
if __name__=='__main__':
    multiprocessing.freeze_support();main()
