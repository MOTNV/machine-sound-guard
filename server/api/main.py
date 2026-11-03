"""api 뼈대: 지금은 /health만 답한다. 기록 저장(POST /api/readings, /api/events)은 다음 PR에서 넣는다."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code, body = (200, {"service": "api", "status": "ok"}) if self.path == "/health" else (404, {"detail": "not found"})
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
