"""Run the same original agent in a browser, without creating another Qt window."""
import multiprocessing
import signal
import threading
import webbrowser
from pathlib import Path
from pcs_agent.config import load
from pcs_agent.instance import InstanceLock
from pcs_agent.runtime import Controller
from pcs_agent.storage import State
from pcs_agent.preview import start_preview

def main():
    config=load();lock=InstanceLock(config['data_dir']);controller=None;server=None
    stopped=threading.Event()
    try:
        controller=Controller(lambda event:None,storage=State(config['data_dir']))
        server=start_preview(config,controller)
        print('Console: '+server.url)
        print('Access key: '+config['preview_key'])
        print('Keep this window open. Press Ctrl+C to stop. Use the desktop Live preview button instead if Strident is already running.')
        webbrowser.open(server.launch_url,new=2)
        signal.signal(signal.SIGINT,lambda *_:stopped.set())
        signal.signal(signal.SIGTERM,lambda *_:stopped.set())
        stopped.wait();return 0
    finally:
        if server:server.close()
        if controller:controller.close()
        lock.close()

if __name__=='__main__':
    multiprocessing.freeze_support()
    try:raise SystemExit(main())
    except Exception as exc:print('Live preview failed: '+str(exc));raise SystemExit(1)
