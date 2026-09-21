"""Ollama-only integration tests: no internet calls, no OpenAI API key or bills."""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine  # noqa: E402
import server  # noqa: E402


@contextmanager
def sandbox():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with (patch.object(engine, 'DATA', root / 'data'),
              patch.object(engine, 'WORKSPACE', root / 'data/workspace'),
              patch.object(engine, 'REPO', root / 'CarveFoundry')):
            engine.WORKSPACE.mkdir(parents=True)
            engine.REPO.mkdir(parents=True)
            engine.init_db()
            # Intentionally do NOT set OPENAI_API_KEY or provider: these are
            # tests of the actual no-credit, local-first default.
            yield root


@contextmanager
def mock_ollama(responses=None):
    requests = []
    responses = responses if responses is not None else []
    class OllamaStub(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != '/api/tags':
                self.send_error(404)
                return
            body = json.dumps({'models': [{'name': 'devstral-small-2:24b'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != '/api/chat':
                self.send_error(404)
                return
            obj = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(obj)
            answer = responses.pop(0) if responses else {
                'message': {'role': 'assistant', 'content': 'Ready to work locally'},
                'done': True, 'prompt_eval_count': 427,
            }
            if obj.get('stream'):
                if isinstance(answer, list):
                    wire = ''.join(json.dumps(x) + '\n' for x in answer).encode()
                else:
                    wire = (json.dumps(answer) + '\n').encode()
                mime = 'application/x-ndjson'
            else:
                if isinstance(answer, list):
                    answer = answer[-1]
                wire = json.dumps(answer).encode()
                mime = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

    http = ThreadingHTTPServer(('127.0.0.1', 0), OllamaStub)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        with patch.object(engine, 'OLLAMA_URL', f'http://127.0.0.1:{http.server_port}'):
            yield requests
    finally:
        http.shutdown()
        http.server_close()


class OllamaTests(unittest.TestCase):
    def test_default_model_and_provider_no_key_required(self):
        with sandbox():
            prefs = engine.get_prefs()
            self.assertEqual(prefs['provider'], 'ollama')
            self.assertEqual(prefs['model'], 'devstral-small-2:24b')
            self.assertEqual(prefs['ollama_ctx'], 16384)
            self.assertEqual(engine.effective_soft_tokens(prefs), 12000)
            with mock_ollama() as calls, patch.object(engine, 'openai_request',
                side_effect=AssertionError('PAID API SHOULD NEVER BE CALLED')):
                tid = engine.new_thread()
                events = []
                with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
                    engine.chat(tid, 'Inspect CarveFoundry offline',
                                lambda typ, data: events.append((typ, data)))
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]['model'], 'devstral-small-2:24b')
                self.assertTrue(calls[0]['stream'])
                self.assertEqual(calls[0]['options']['num_ctx'], 16384)
                self.assertEqual(calls[0]['messages'][0]['role'], 'system')
                self.assertIn('CarveFoundry', calls[0]['messages'][0]['content'])
                self.assertEqual(calls[0]['messages'][-1]['content'],
                                 'Inspect CarveFoundry offline')
                self.assertEqual(len(calls[0]['tools']), len(engine.TOOLS))
                self.assertTrue(any(kind == 'done' for kind, _ in events))
                self.assertEqual(engine.get_thread(tid)['last_input_tokens'], 427)

    def test_tool_rounds_and_approval_remain_functional(self):
        with sandbox():
            first = [
                {'message': {'role': 'assistant', 'content': 'Checking your project…'},
                 'done': False},
                {'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'function': {'name': 'write_file', 'arguments': {
                        'path': 'workspace/offline-report.md',
                        'content': 'Local-only test'}}} ]}, 'done': True,
                 'prompt_eval_count': 244},
            ]
            second = [
                {'message': {'role': 'assistant', 'content': 'Completed without API.'},
                 'done': True, 'prompt_eval_count': 384}
            ]
            with mock_ollama([first, second]) as calls:
                tid = engine.new_thread()
                approvals = []
                def tell(kind, data):
                    if kind == 'approval':
                        approvals.append(data)
                        engine.APPROVALS.decide(data['id'], True)
                engine.chat(tid, 'Make an offline report', tell)
                self.assertEqual(engine.read_file('workspace/offline-report.md'),
                                 'Local-only test')
                self.assertEqual(len(approvals), 1)
                self.assertEqual(len(calls), 2)
                self.assertTrue(any(m['role'] == 'tool'
                                    for m in calls[1]['messages']))
                self.assertTrue(any(m['role'] == 'assistant'
                                    and m.get('tool_calls')
                                    for m in calls[1]['messages']))
                self.assertIn('Completed without API.',
                              engine.get_thread(tid)['messages'][-1]['content'])

    def test_ollama_image_converts_to_raw_base64_images(self):
        with sandbox():
            image = engine.WORKSPACE / 'uploads/picture.png'
            image.parent.mkdir()
            image.write_bytes(b'fake-image-bytes')
            with mock_ollama() as calls:
                tid = engine.new_thread()
                engine.chat(tid, 'What is in the picture?', lambda *_: None,
                            attachments=['workspace/uploads/picture.png'])
                user = calls[0]['messages'][-1]
                self.assertEqual(user['role'], 'user')
                self.assertIn('picture', user['content'])
                self.assertEqual(base64.b64decode(user['images'][0]),
                                 b'fake-image-bytes')
                self.assertNotIn('data:image', user['images'][0])

    def test_local_handover_and_fallback_with_zero_openai_key(self):
        with sandbox():
            engine.set_pref('max_turns', '3')
            old = engine.new_thread()
            for i in range(3):
                engine.append(old, 'user', f'CarveFoundry CNC detail {i}')
                engine.append(old, 'assistant', f'Preserved response {i}')
            summary = {'message': {'content': 'HANDOVER: CarveFoundry active, context preserved. '
                                    'Check prior decisions and repo source before proceeding.'}}
            with mock_ollama([summary, {'message': {'content': 'Done locally'},
                                          'done': True, 'prompt_eval_count': 610}]) as calls:
                events = []
                new = engine.chat(old, 'Continue at full local resolution',
                                  lambda typ, data: events.append((typ, data)))
            self.assertEqual(len(calls), 2)
            self.assertFalse(calls[0]['stream'])
            self.assertTrue(calls[1]['stream'])
            self.assertNotEqual(new, old)
            self.assertTrue(engine.get_thread(old)['archived'])
            self.assertEqual([m['role'] for m in engine.get_thread(new)['messages']],
                             ['handoff', 'user', 'assistant'])
            self.assertIn('HANDOVER:', engine.get_thread(new)['summary'])
            self.assertTrue(any(kind == 'rollover' for kind, _ in events))
            # When local Ollama is down, manual handover still preserves chat.
            orphan = engine.new_thread()
            engine.append(orphan, 'user', 'Keep all details when offline')
            with patch.object(engine, 'ollama_once', side_effect=RuntimeError('offline')):
                continuation, handover = engine.summarize_and_roll(orphan)
            self.assertIn('offline', handover)
            self.assertIn('Keep all details', handover)
            self.assertEqual(engine.get_thread(continuation)['previous_id'], orphan)

    def test_no_silent_fallback_to_paid_openai_when_local_unavailable(self):
        with sandbox():
            with patch.object(engine, 'ollama_status', return_value={
                'online': False, 'installed': False, 'message': 'Offline'}), \
                 patch.object(engine, 'openai_request',
                   side_effect=AssertionError('Never fallback to paid API')):
                tid = engine.new_thread()
                with self.assertRaisesRegex(RuntimeError, 'Offline'):
                    engine.chat(tid, 'Do not charge me', lambda *_: None)
                self.assertEqual(engine.get_thread(tid)['messages'], [])

    def test_openai_remains_explicit_only_and_preserves_old_setting(self):
        with sandbox():
            engine.set_pref('model', 'previous-api-model')
            self.assertEqual(engine.get_prefs()['model'], 'devstral-small-2:24b')
            engine.set_pref('provider', 'openai')
            self.assertEqual(engine.get_prefs()['model'], 'previous-api-model')
            engine.set_pref('ollama_model', 'devstral-small-2:latest')
            engine.set_pref('provider', 'ollama')
            self.assertEqual(engine.get_prefs()['model'], 'devstral-small-2:latest')
            with self.assertRaisesRegex(ValueError, 'Cloud-hosted'):
                engine.set_pref('ollama_model', 'devstral-small-2:24b-cloud')
            for unsafe in ('http://example.org:11434', 'https://localhost:11434',
                           'http://127.0.0.1:11434@remote.io'):
                with patch.object(engine, 'OLLAMA_URL', unsafe):
                    with self.assertRaises(ValueError):
                        engine.ollama_base_url()
            with self.assertRaises(ValueError):
                engine.safe_path('repo/ai.key')

    def test_actual_browser_send_sse_uses_ollama_without_paid_provider(self):
        with sandbox(), mock_ollama() as calls, \
             patch.object(engine, 'openai_request',
                          side_effect=AssertionError('OpenAI calls forbidden')):
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.AppHandler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                base = f'http://127.0.0.1:{http.server_port}'
                req = urllib.request.Request(base + '/api/thread',
                    b'{"title":"Local chat"}', {'Content-Type': 'application/json'},
                    method='POST')
                with urllib.request.urlopen(req, timeout=5) as response:
                    thread_id = json.load(response)['thread_id']
                payload = json.dumps({'thread_id': thread_id,
                                      'text': 'Work without OpenAI credits'}).encode()
                req = urllib.request.Request(base + '/api/send', payload,
                    {'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    sse = response.read().decode()
                self.assertIn('event: done', sse)
                self.assertIn('Ready to work locally', sse)
                self.assertEqual(len(calls), 1)
                self.assertEqual(engine.get_thread(thread_id)['messages'][-1]['role'],
                                 'assistant')
            finally:
                http.shutdown()
                http.server_close()

    def test_ui_has_persistent_copyable_error_and_provider_controls(self):
        page = (Path(__file__).resolve().parents[1] / 'static/index.html').read_text()
        js = (Path(__file__).resolve().parents[1] / 'static/app.js').read_text()
        self.assertIn('id="settingProvider"', page)
        self.assertIn('id="copyError"', page)
        self.assertIn('id="errorPanel"', page)
        self.assertIn("$('#errorPanel').classList.remove('hidden')", js)
        self.assertIn("navigator.clipboard.writeText", js)
        self.assertIn("KEY SET · CREDITS UNVERIFIED", js)

    def test_api_settings_http_switch_does_not_need_openai_key(self):
        with sandbox(), mock_ollama():
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.AppHandler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            def req(route, payload=None):
                request = urllib.request.Request(
                    base + route, json.dumps(payload).encode() if payload is not None else None,
                    {'Content-Type': 'application/json'} if payload is not None else {},
                    method='POST' if payload is not None else 'GET')
                with urllib.request.urlopen(request, timeout=5) as resp:
                    return json.load(resp)
            try:
                state = req('/api/state')
                self.assertEqual(state['settings']['provider'], 'ollama')
                self.assertTrue(state['ollama']['online'])
                self.assertTrue(state['ollama']['installed'])
                self.assertFalse(state['has_api_key']) if not engine.api_key() else None
                settings = req('/api/settings', {'provider': 'ollama',
                    'model': 'devstral-small-2:24b', 'ollama_ctx': 16384,
                    'soft_tokens': 11000, 'web_search': 0})
                self.assertEqual(settings['model'], 'devstral-small-2:24b')
                self.assertEqual(settings['soft_tokens'], 11000)
                self.assertEqual(settings['provider'], 'ollama')
            finally:
                http.shutdown()
                http.server_close()


if __name__ == '__main__':
    unittest.main()
