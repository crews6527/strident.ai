"""A browser and phone surface over the existing desktop Controller."""
import secrets
from .config import save
from .server import ConsoleServer

TERMINAL={'complete','answered','needs_attention','failed','cancelled','interrupted'}

class PreviewRuntime:
    def __init__(self,config,controller):
        self.config=config;self.controller=controller;self.store=controller.journal;self.guard=controller.lock
        if not self.store:raise RuntimeError('Task storage must be available for the live preview.')
    def submit(self,prompt):return self.controller.submit(prompt,self.config)
    def cancel(self,ident):
        self.store.get(ident);self.controller.cancel_task(ident)
    def retry(self,ident):
        task=self.store.get(ident)
        if task['status'] not in TERMINAL:raise ValueError('Task is still active.')
        return self.submit(task['prompt'])

def start_preview(config,controller,port=None):
    if not config.get('preview_key'):
        config['preview_key']=secrets.token_urlsafe(32);save(config)
    return ConsoleServer(config,PreviewRuntime(config,controller),port).start()
