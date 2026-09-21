"""CarveWork local web server: python server.py (Python 3.11+, no pip install)."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engine

HERE = Path(__file__).resolve().parent
STATIC = HERE / 'static'
MAX_REQUEST = 5 * 1024 * 1024


class AppHandler(BaseHTTPRequestHandler):
    server_version = 'CarveWork/1.0'

    def log_message(self, fmt, *args):
        print(f'[CarveWork] {self.address_string()} ' + fmt % args, flush=True)

    def json_response(self, data, status=200):
        data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def static_file(self, path: Path):
        if not path.is_file() or not path.resolve().is_relative_to(STATIC.resolve()):
            self.send_error(404); return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> dict:
        size = int(self.headers.get('Content-Length', '0'))
        if size < 1 or size > MAX_REQUEST:
            raise ValueError('Request must be 1 byte–5 MB')
        raw = json.loads(self.rfile.read(size))
        if not isinstance(raw, dict): raise ValueError('Expected JSON object')
        return raw

    def _check_host(self) -> bool:
        # Bound to loopback: do not expose local repo, approvals or API key
        # through reverse-proxy / DNS rebinding without explicit redesign.
        host = self.headers.get('Host','').split(':')[0]
        if host not in ('localhost','127.0.0.1','[::1]','::1'):
            self.send_error(403,'Localhost only')
            return False
        origin = self.headers.get('Origin','')
        if origin and not re.match(r'^https?://(localhost|127\.0\.0\.1|\[::1\]):\d+$',origin):
            self.send_error(403,'Untrusted request origin')
            return False
        return True

    def do_GET(self):
        if not self._check_host(): return
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == '/': return self.static_file(STATIC / 'index.html')
            if parsed.path in ('/app.css','/app.js'):
                return self.static_file(STATIC / parsed.path[1:])
            if parsed.path == '/api/state':
                threads = engine.threads()
                if not threads:
                    engine.new_thread()
                    threads = engine.threads()
                return self.json_response({
                    'threads':threads, 'tasks':engine.all_tasks(), 'workspace':engine.list_files(),
                    'repo':engine.list_files('repo') if engine.REPO else [],
                    'repo_path':str(engine.REPO) if engine.REPO else '',
                    'has_api_key':bool(engine.api_key()),'settings':engine.get_prefs(),
                    'ollama':engine.ollama_status(),
                    'approvals':[{'id':k,'name':v['name'],'details':v['details']}
                                 for k,v in engine.APPROVALS.pending.items()]})
            if parsed.path == '/api/thread':
                return self.json_response(engine.get_thread(params.get('id',[''])[0]))
            if parsed.path == '/api/file':
                return self.json_response({'text':engine.read_file(params.get('path',[''])[0])})
            if parsed.path == '/api/raw':
                label=params.get('path',[''])[0]
                file=engine.safe_path(label)
                if not file.is_file() or file.stat().st_size>engine.MAX_UPLOAD:
                    raise ValueError('No file or file too large')
                mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                self.send_response(200)
                self.send_header('Content-Type',mime)
                self.send_header('Content-Disposition','inline' if mime.startswith('image/') else 'attachment')
                self.send_header('Content-Length',str(file.stat().st_size))
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers();self.wfile.write(file.read_bytes());return
            self.send_error(404)
        except (ValueError,OSError) as exc:
            return self.json_response({'error':str(exc)},400)

    def do_POST(self):
        if not self._check_host(): return
        try:
            data=self.body()
            route=urllib.parse.urlparse(self.path).path
            if route == '/api/thread':
                return self.json_response({'thread_id':engine.new_thread(data.get('title') or 'New chat')})
            if route == '/api/rollover':
                with engine.APP_LOCK:
                    tid, summary=engine.summarize_and_roll(str(data['thread_id']))
                return self.json_response({'thread_id':tid,'handover':summary})
            if route == '/api/approval':
                ok=engine.APPROVALS.decide(str(data.get('id','')),data.get('approve') is True)
                return self.json_response({'ok':ok},200 if ok else 404)
            if route == '/api/settings':
                if 'provider' in data:
                    engine.set_pref('provider', str(data['provider']))
                for k,v in data.items():
                    if k == 'provider':
                        continue
                    if k == 'model':
                        key = ('ollama_model' if engine.get_prefs()['provider'] == 'ollama'
                               else 'openai_model')
                        engine.set_pref(key, str(v))
                    else:
                        engine.set_pref(k, str(v))
                return self.json_response(engine.get_prefs())
            if route == '/api/file/save':
                label=str(data['path'])
                if not label.startswith('workspace/'):
                    raise ValueError('Direct editing is only available for workspace files; repo edits require agent approval')
                return self.json_response({'result':engine.write_file(label,str(data['content']))})
            if route == '/api/task':
                return self.json_response(engine.add_task(str(data['title']),str(data.get('details',''))))
            if route == '/api/task/complete':
                return self.json_response(engine.complete_task(str(data['id'])))
            if route == '/api/upload':
                name=Path(str(data.get('name','upload.bin'))).name
                if not name or name in ('.','..') or name.startswith('.'):
                    raise ValueError('Invalid filename')
                if len(name)>110: raise ValueError('Filename too long')
                raw=base64.b64decode(data['base64'],validate=True)
                if len(raw)>engine.MAX_UPLOAD: raise ValueError('Maximum upload 3 MB')
                target='workspace/uploads/'+uuid.uuid4().hex[:8]+'-'+name
                file=engine.safe_path(target,write=True)
                file.parent.mkdir(parents=True,exist_ok=True)
                file.write_bytes(raw)
                return self.json_response({'path':target,'bytes':len(raw)})
            if route == '/api/send':
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream; charset=utf-8')
                self.send_header('Cache-Control','no-cache, no-transform')
                self.send_header('X-Accel-Buffering','no')
                self.send_header('Connection','close')
                self.end_headers()
                def send(kind, obj):
                    wire=('event: '+kind+'\ndata: '+json.dumps(obj,ensure_ascii=False)+'\n\n').encode()
                    self.wfile.write(wire);self.wfile.flush()
                try:
                    engine.chat(str(data['thread_id']),str(data.get('text','')),send,list(data.get('attachments') or []))
                except Exception as exc:
                    try:send('error',{'message':str(exc)})
                    except (ConnectionError,BrokenPipeError):pass
                return
            self.send_error(404)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return self.json_response({'error':str(exc)},400)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='CarveWork: work-style local AI project chat with automatic handover.')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    engine.init_db()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),AppHandler)
    server.daemon_threads=True
    url=f'http://127.0.0.1:{args.port}'
    print(f'\nCarveWork ready: {url}',flush=True)
    prefs = engine.get_prefs()
    if prefs['provider'] == 'ollama':
        status = engine.ollama_status()
        print(f'AI: local Ollama ({prefs["ollama_model"]}): {status["message"]}', flush=True)
        print('OpenAI API requests: DISABLED (no API usage charges)', flush=True)
    else:
        print(f'AI: OpenAI API ({prefs["openai_model"]}) — '
              f'{"key configured; credits not checked" if engine.api_key() else "MISSING OPENAI_API_KEY"}',
              flush=True)
    print(f'Local repo: {engine.REPO or "not linked"}',flush=True)
    print('Stop: Ctrl+C\n',flush=True)
    try:server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
