"""Shared queue, API authentication, persistence and real process supervision."""
import http.client
import json
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch
from pcs_agent.config import validate
from pcs_agent.runtime import Controller
from pcs_agent.storage import State
from pcs_agent.preview import start_preview
from pcs_agent.trace import Store
from enable_phone import configure_host


def progress_worker(pipe, command, config, attachment, history):
    duration=float(command)
    start=time.monotonic()
    while time.monotonic()-start<duration:
        pipe.send({'kind':'model_progress','received_bytes':1})
        pipe.send({'kind':'delta','text':'.'})
        time.sleep(0.25)
    pipe.send({'kind':'result','status':'complete','summary':'Progressing worker finished.','reply':'finished','evidence':[]});pipe.close()

def partial_worker(pipe, command, config, attachment, history):
    pipe.send({'kind':'delta','text':'Retain this partial answer.'})
    time.sleep(30);pipe.close()

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.config=validate({'data_dir':str(root/'data'),'workspace':str(root),'preview_key':'k'*43})
        self.events=queue.Queue();self.controller=Controller(self.events.put,storage=State(self.config['data_dir']))
        self.server=start_preview(self.config,self.controller,port=0)
    def tearDown(self):
        self.server.close();self.controller.close();self.temp.cleanup()
    def request(self,path,body=None,key='k'*43,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.httpd.server_port,timeout=5)
        try:
            h={'Authorization':'Bearer '+key,'Content-Type':'application/json',**(headers or {})}
            conn.request('POST' if body is not None else 'GET',path,None if body is None else json.dumps(body),h)
            response=conn.getresponse();raw=response.read()
            return response.status,json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw
        finally:conn.close()
    def wait(self,ident):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            task=self.controller.journal.get(ident)
            if task['status'] not in ('queued','running'):return task
            time.sleep(0.03)
        self.fail('Task did not complete.')
    def test_browser_to_real_spawned_tool_result_and_export(self):
        code,data=self.request('/api/tasks',{'prompt':'Help'});self.assertEqual(code,202)
        task=self.wait(data['id']);self.assertEqual(task['status'],'complete');self.assertIn('Ready for tasks',task['result'])
        code,events=self.request('/api/events?task='+data['id']);self.assertEqual(code,200)
        self.assertTrue(any(e['kind']=='tool' for e in events))
        code,data=self.request('/api/export');serialized=json.dumps(data)
        self.assertIn('Help',serialized);self.assertNotIn('k'*43,serialized)
        self.assertEqual(len(data['tasks']),1)
    def test_auth_host_origin_and_body_validation(self):
        self.assertEqual(self.request('/api/tasks',key='wrong')[0],401)
        self.assertEqual(self.request('/api/tasks',headers={'Host':'evil.test'})[0],403)
        self.assertEqual(self.request('/api/tasks',headers={'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.request('/api/tasks',{'prompt':''})[0],400)
        self.assertEqual(self.request('/api/config',{'preview_key':'replaced'})[0],400)
        self.assertEqual(self.request('/api/events?task=absent')[0],404)
        self.assertEqual(self.request('/../config.json')[0],404)
        code,config=self.request('/api/config');self.assertEqual(code,200);self.assertNotIn('preview_key',config)
        self.assertEqual(self.request('/')[0],200)
    def test_explicit_retry_uses_new_id_and_persistent_trace(self):
        code,data=self.request('/api/tasks',{'prompt':'Help'});self.wait(data['id'])
        code,new=self.request('/api/retry',{'id':data['id']});self.assertEqual(code,202);self.assertNotEqual(new['id'],data['id'])
        self.wait(new['id']);self.assertEqual(len(Store(self.config['data_dir']).tasks()),2)
    def test_phone_host_validation_and_no_secret_in_export(self):
        cfg=configure_host(self.config,'desktop.tail123.ts.net.')
        self.assertIn('desktop.tail123.ts.net',cfg['preview_hosts'])
        with self.assertRaises(ValueError):configure_host(self.config,'public.example.com')
    def test_settings_validated_before_save(self):
        self.assertEqual(self.request('/api/config',{'model_timeout':0})[0],400)
        with patch('pcs_agent.server.save') as save:
            code,_=self.request('/api/config',{'model_timeout':30})
        self.assertEqual(code,200);save.assert_called_once();self.assertEqual(self.config['model_timeout'],30)

class SupervisionTests(unittest.TestCase):
    def wait_result(self,events,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            event=events.get(timeout=max(.1,deadline-time.monotonic()))
            if event['kind']=='result':return event
        self.fail('No completion event.')
    def test_real_progress_renews_inactivity_budget(self):
        events=queue.Queue();controller=Controller(events.put,worker=progress_worker)
        try:
            controller.submit('6',validate({'task_timeout':5,'max_task_seconds':20}))
            result=self.wait_result(events,10);self.assertEqual(result['status'],'complete')
        finally:controller.close()
    def test_overall_ceiling_stops_continuous_progress(self):
        events=queue.Queue();controller=Controller(events.put,worker=progress_worker)
        try:
            controller.submit('30',validate({'task_timeout':5,'max_task_seconds':5}))
            result=self.wait_result(events,8);self.assertEqual(result['status'],'failed');self.assertIn('overall task',result['summary']);self.assertTrue(result['reply'])
        finally:controller.close()
    def test_partial_answer_retained_on_cancel(self):
        events=queue.Queue();controller=Controller(events.put,worker=partial_worker)
        try:
            ident=controller.submit('wait',validate({}))
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if events.get(timeout=5)['kind']=='delta':break
            controller.cancel_task(ident);result=self.wait_result(events,5)
            self.assertEqual(result['status'],'cancelled');self.assertEqual(result['reply'],'Retain this partial answer.')
        finally:controller.close()
    def test_stale_tasks_marked_interrupted_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Store(folder);ident=s.create('Never replay an action automatically');s.update(ident,status='running');s.recover()
            self.assertEqual(s.get(ident)['status'],'interrupted')

if __name__=='__main__':unittest.main()
