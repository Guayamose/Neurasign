#!/usr/bin/env python3
"""Internal stdlib HTTP server. Only reviewed anonymous dataset records are accepted."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from runtime import ModelRuntime, RuntimeErrorResponse, ensure_research_environment

MAX_BODY = 2048


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field')
        value[key] = item
    return value


def invalid_constant(_):
    raise ValueError('Nonfinite JSON')


def handler_for(runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ModelResearch'
        def setup(self):
            super().setup(); self.connection.settimeout(10)
        def log_message(self, *_):
            pass
        def send_json(self, status, payload):
            raw = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(raw)
        def dispatch(self):
            if '?' in self.path or len(self.path) > 200:
                raise RuntimeErrorResponse(422, 'invalid_request')
            if self.command == 'GET':
                if self.path == '/health': return runtime.health()
                if self.path == '/catalog': return runtime.public_catalog()
                match = re.fullmatch(r'/models/([a-z]+)/records', self.path)
                if match: return runtime.records(match[1])
            if self.command == 'POST':
                match = re.fullmatch(r'/models/([a-z]+)/predict', self.path)
                if match:
                    if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                        raise RuntimeErrorResponse(422, 'invalid_request')
                    length = self.headers.get('Content-Length', '')
                    if not length.isdigit() or not 0 < int(length) <= MAX_BODY:
                        raise RuntimeErrorResponse(422, 'invalid_request')
                    if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                        raise RuntimeErrorResponse(422, 'invalid_request')
                    try:
                        raw = self.rfile.read(int(length))
                        if len(raw) != int(length): raise ValueError('Truncated body')
                        body = json.loads(raw, object_pairs_hook=strict_object, parse_constant=invalid_constant)
                    except (UnicodeError, ValueError, OSError):
                        raise RuntimeErrorResponse(422, 'invalid_request') from None
                    return runtime.predict(match[1], body)
            raise RuntimeErrorResponse(404, 'unknown_route')
        def respond(self):
            try:
                self.send_json(200, self.dispatch())
            except RuntimeErrorResponse as error:
                self.send_json(error.status, {'error': error.code})
            except Exception:
                self.send_json(503, {'error': 'service_unavailable'})
        do_GET = respond
        do_POST = respond
    return Handler


def main():
    ensure_research_environment()
    runtime = ModelRuntime()
    server = ThreadingHTTPServer((os.getenv('MODEL_ENGINE_HOST', '127.0.0.1'), int(os.getenv('PORT', '8010'))), handler_for(runtime))
    server.daemon_threads = True
    server.serve_forever()


if __name__ == '__main__':
    main()
