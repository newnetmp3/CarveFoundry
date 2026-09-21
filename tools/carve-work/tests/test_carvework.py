"""Deterministic functional tests; no real API token or repository mutation."""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine  # noqa: E402
import server  # noqa: E402


@contextmanager
def sandbox():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        with patch.object(engine,'DATA',root/'data'), patch.object(engine,'WORKSPACE',root/'data'/'workspace'), patch.object(engine,'REPO',root/'repo'):
            engine.WORKSPACE.mkdir(parents=True)
            engine.REPO.mkdir(parents=True)
            engine.init_db()
            engine.set_pref('provider', 'openai')  # Legacy API regression tests.
            yield root


class EngineTests(unittest.TestCase):
    def test_persists_threads_and_tasks(self):
        with sandbox():
            one=engine.new_thread()
            engine.append(one,'user','Please work on CarveFoundry')
            engine.append(one,'assistant','I will inspect the repo.')
            self.assertEqual(engine.get_thread(one)['title'],'Please work on CarveFoundry')
            self.assertEqual(len(engine.get_thread(one)['messages']),2)
            task=engine.add_task('Test UI','On actual KDE')
            self.assertEqual(engine.complete_task(task['id']),{'completed':task['id']})
            self.assertEqual(engine.all_tasks()[0]['done'],1)

    def test_auto_handover_keeps_full_old_transcript_and_avoids_duplicates(self):
        with sandbox(),patch.object(engine,'api_key',return_value='fake'):
            tid=engine.new_thread()
            engine.set_pref('max_turns','3')
            for i in range(3):
                engine.append(tid,'user',f'User message {i} about exact CNC constraints')
                engine.append(tid,'assistant',f'Assistant answer {i}')
            events=[]
            def emit(kind,data):events.append((kind,data))
            def fake_summary(payload):
                self.assertIn(tid,payload['input'])
                return {'output':[{'type':'message','content':[{'type':'output_text','text':
                    'HANDOVER: CarveFoundry user needs continued work; all three prior requests and edits are recorded. Original thread is preserved.'}]}]}
            def fake_stream(payload):
                self.assertIn('HANDOVER',payload['instructions'])
                self.assertEqual(payload['input'][-1]['content'],'Please continue and finish the test')
                yield {'type':'delta','text':'Ready'}
                yield {'type':'response','response':{'output':[{'type':'message','content':[{'type':'output_text','text':'Ready'}]}],
                            'usage':{'input_tokens':1200}}}
            with patch.object(engine,'api_once',side_effect=fake_summary),patch.object(engine,'stream_response',side_effect=fake_stream):
                new=engine.chat(tid,'Please continue and finish the test',emit)
            self.assertNotEqual(tid,new)
            self.assertEqual(engine.get_thread(tid)['archived'],1)
            self.assertEqual(len(engine.get_thread(tid)['messages']),6)
            messages=engine.get_thread(new)['messages']
            self.assertEqual([m['role'] for m in messages],['handoff','user','assistant'])
            self.assertEqual(messages[-2]['content'],'Please continue and finish the test')
            self.assertTrue(any(kind=='rollover' for kind,_ in events))
            self.assertEqual(messages[-1]['content'],'Ready')
            self.assertEqual(engine.get_thread(new)['previous_id'],tid)

    def test_summary_failover_never_loses_transcript(self):
        with sandbox():
            tid=engine.new_thread()
            engine.append(tid,'user','Preserve details XYZ origin stock bottom-left')
            with patch.object(engine,'api_once',side_effect=RuntimeError('quota')):
                new,summary=engine.summarize_and_roll(tid)
            self.assertIn('Preserve details XYZ',summary)
            self.assertIn('quota',summary)
            self.assertEqual(engine.get_thread(tid)['messages'][0]['role'],'user')
            self.assertEqual(engine.get_thread(new)['summary'],summary)

    def test_safe_paths_symlinks_secrets_and_approved_write(self):
        with sandbox() as root:
            engine.write_file('workspace/notes/plan.md','Test file')
            self.assertEqual(engine.read_file('workspace/notes/plan.md'),'Test file')
            self.assertTrue(any(item['path']=='workspace/notes/plan.md' and item['line']==1
                                for item in engine.search_files('workspace','test')))
            self.assertTrue(any(f['path']=='workspace/notes/plan.md' for f in engine.list_files()))
            for illegal in ['workspace/../test', 'repo/.git/config','repo/.env','/etc/passwd',
                            'workspace/.venv/secret','repo/../../etc/passwd']:
                with self.subTest(illegal=illegal),self.assertRaises(ValueError):engine.safe_path(illegal)
            (engine.WORKSPACE/'escape').symlink_to(root)
            with self.assertRaises(ValueError):engine.safe_path('workspace/escape/outside.txt',write=True)
            events=[]
            def send(kind,data):events.append((kind,data));
            def auto_decide(kind,data):
                send(kind,data)
                if kind=='approval':engine.APPROVALS.decide(data['id'],True)
            result=engine.tool_exec('write_file',{'path':'workspace/test.py','content':'print(1)'},auto_decide)
            self.assertIn('"ok": true',result)
            self.assertEqual(engine.read_file('workspace/test.py'),'print(1)')
            # Rejected write does not alter existing file.
            def deny(kind,data):
                if kind=='approval':engine.APPROVALS.decide(data['id'],False)
            engine.tool_exec('write_file',{'path':'workspace/test.py','content':'BAD'},deny)
            self.assertEqual(engine.read_file('workspace/test.py'),'print(1)')

    def test_approved_command_has_real_exit_status(self):
        with sandbox():
            def approve(kind,data):
                if kind=='approval':engine.APPROVALS.decide(data['id'],True)
            result=json.loads(engine.tool_exec('run_command',
                {'root':'workspace','command':'python3 -c "print(41+1)"'},approve))
            self.assertEqual(result['result']['exit_code'],0)
            self.assertIn('42',result['result']['output'])

    def test_archive_can_be_read_and_searched_by_new_chat(self):
        with sandbox():
            old=engine.new_thread()
            engine.append(old,'user','Fence is twenty-three millimeters tall')
            engine.append(old,'assistant','Remember the fixture height before rapids')
            new=engine.new_thread(previous_id=old,summary='handover')
            history=engine.read_chat_history(old,0,20)
            self.assertEqual(history['total_messages'],2)
            self.assertEqual(history['messages'][0]['role'],'user')
            self.assertEqual(engine.get_thread(new)['previous_id'],old)
            results=engine.search_chat_history('twenty-three')
            self.assertEqual(results[0]['thread_id'],old)
            self.assertIn('Fence',results[0]['content'])

    def test_sse_text_and_tool_workflow(self):
        with sandbox(),patch.object(engine,'api_key',return_value='test'):
            tid=engine.new_thread()
            output=[]
            events=[]
            def fake_stream(payload):
                output.append(payload)
                if len(output)==1:
                    yield {'type':'delta','text':'Looking at files. '}
                    yield {'type':'response','response':{'output':[
                        {'type':'message','role':'assistant','content':[{'type':'output_text','text':'Looking at files. '}]},
                        {'type':'function_call','call_id':'call_1','name':'list_files','arguments':'{"root":"workspace"}'}]}}
                else:
                    self.assertEqual(payload['input'][-1]['type'],'function_call_output')
                    self.assertIn('PROJECT_CONTEXT.md',payload['input'][-1]['output'])
                    yield {'type':'delta','text':'Done.'}
                    yield {'type':'response','response':{'output':[{'type':'message','content':[{'type':'output_text','text':'Done.'}]}]}}
            with patch.object(engine,'stream_response',side_effect=fake_stream):
                engine.chat(tid,'Inspect files',lambda kind,data:events.append((kind,data)))
            self.assertEqual(len(output),2)
            self.assertEqual(engine.get_thread(tid)['messages'][-1]['content'],'Looking at files. Done.')
            self.assertTrue(any(kind=='done' for kind,_ in events))

    def test_real_http_sse_parser_and_api_key_header_without_external_api(self):
        with sandbox():
            received=[]
            class MockAPI(BaseHTTPRequestHandler):
                def do_POST(self):
                    payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    received.append((payload,self.headers.get('Authorization')))
                    if payload.get('stream'):
                        events=[
                          {'type':'response.output_text.delta','delta':'Hello '},
                          {'type':'response.output_text.delta','delta':'world'},
                          {'type':'response.completed','response':{'output':[{'type':'message',
                            'content':[{'type':'output_text','text':'Hello world'}]}]}}
                        ]
                        body=''.join('data: '+json.dumps(x)+'\n\n' for x in events).encode()
                    else:
                        body=json.dumps({'output':[{'type':'message','content':[
                            {'type':'output_text','text':'HANDOVER preserved'}]}]}).encode()
                    self.send_response(200);self.send_header('Content-Type',
                        'text/event-stream' if payload.get('stream') else 'application/json')
                    self.send_header('Content-Length',str(len(body)))
                    self.end_headers();self.wfile.write(body)
                def log_message(self,*args):pass
            http=ThreadingHTTPServer(('127.0.0.1',0),MockAPI)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with patch.object(engine,'API_URL',f'http://127.0.0.1:{http.server_port}/responses'), \
                     patch.object(engine,'api_key',return_value='mock-secret'):
                    result=list(engine.stream_response({'model':'demo','input':'Hi'}))
                    summary=engine.api_once({'model':'demo','input':'Summarize'})
                self.assertEqual([x['text'] for x in result if x['type']=='delta'],
                                 ['Hello ','world'])
                self.assertEqual(engine.extract_text(result[-1]['response']),'Hello world')
                self.assertIn('HANDOVER',engine.extract_text(summary))
                self.assertEqual(received[0][1],'Bearer mock-secret')
                self.assertTrue(received[0][0]['stream'])
                self.assertFalse(received[0][0]['store'])
            finally:http.shutdown();http.server_close()

    def test_image_attachment_reaches_model_as_real_input_image(self):
        with sandbox(),patch.object(engine,'api_key',return_value='mock'):
            image=engine.WORKSPACE/'uploads'/'picture.png'
            image.parent.mkdir();image.write_bytes(b'fake PNG bytes for transport test')
            tid=engine.new_thread()
            seen=[]
            def fake_stream(payload):
                seen.append(payload)
                yield {'type':'response','response':{'output':[{'type':'message',
                    'content':[{'type':'output_text','text':'I received an image'}]}]}}
            with patch.object(engine,'stream_response',side_effect=fake_stream):
                engine.chat(tid,'What is shown?',lambda *_:None,
                            attachments=['workspace/uploads/picture.png'])
            inp=seen[0]['input'][-1]['content']
            self.assertEqual(inp[0]['type'],'input_text')
            self.assertEqual(inp[1]['type'],'input_image')
            self.assertIn('data:image/png;base64,',inp[1]['image_url'])
            self.assertEqual(len(engine.get_thread(tid)['messages']),2)

    def test_optional_web_research_is_explicit_opt_in(self):
        with sandbox(),patch.object(engine,'api_key',return_value='mock'):
            engine.set_pref('web_search','1')
            tid=engine.new_thread()
            requests=[]
            def fake_stream(payload):
                requests.append(payload)
                yield {'type':'response','response':{'output':[{'type':'message',
                    'content':[{'type':'output_text','text':'Done'}]}]}}
            with patch.object(engine,'stream_response',side_effect=fake_stream):
                engine.chat(tid,'Research this',lambda *_:None)
            self.assertTrue(any(t.get('type')=='web_search' for t in requests[0]['tools']))

    def test_unexpected_context_error_creates_new_chat_without_duplicate_turn(self):
        with sandbox(),patch.object(engine,'api_key',return_value='test'):
            tid=engine.new_thread()
            calls=[]
            def flaky_stream(payload):
                calls.append(payload)
                if len(calls)==1: raise RuntimeError('context_length_exceeded')
                yield {'type':'response','response':{'output':[{'type':'message','content':[{'type':'output_text','text':'Recovered'}]}]}}
            with patch.object(engine,'stream_response',side_effect=flaky_stream),patch.object(engine,'api_once',side_effect=RuntimeError('no summary')):
                new=engine.chat(tid,'Keep my new request',lambda *_:None)
            self.assertNotEqual(new,tid)
            self.assertEqual(sum(x['role']=='user' for x in engine.get_thread(tid)['messages']),0)
            self.assertEqual(sum(x['role']=='user' for x in engine.get_thread(new)['messages']),1)
            self.assertIn('Keep my new request',engine.get_thread(new)['messages'][-2]['content'])


class APITests(unittest.TestCase):
    def test_http_frontend_state_thread_and_upload(self):
        with sandbox():
            http=ThreadingHTTPServer(('127.0.0.1',0),server.AppHandler)
            worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{http.server_port}'
            def request(route,payload=None):
                obj=urllib.request.Request(base+route,
                    json.dumps(payload).encode() if payload is not None else None,
                    {'Content-Type':'application/json'} if payload is not None else {},
                    method='POST' if payload is not None else 'GET')
                with urllib.request.urlopen(obj,timeout=3) as resp:return json.loads(resp.read())
            try:
                self.assertGreater(len(request('/api/state')['threads']),0)
                t=request('/api/thread',{'title':'Functional chat'})['thread_id']
                self.assertEqual(request('/api/thread?id='+t)['title'],'Functional chat')
                uploaded=request('/api/upload',{'name':'test.txt',
                                 'base64':base64.b64encode(b'Hello CarveWork').decode()})['path']
                self.assertEqual(request('/api/file?path='+uploaded)['text'],'Hello CarveWork')
                self.assertTrue(request('/api/task',{'title':'Review source'})['id'])
                self.assertEqual(request('/api/state')['tasks'][0]['title'],'Review source')
            finally:http.shutdown();http.server_close()


if __name__=='__main__':unittest.main()
