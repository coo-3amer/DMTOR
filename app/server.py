"""Local HTTP bridge (127.0.0.1 only) that receives downloads from the browser extension."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 9614
from features import VERSION


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False   # so a second copy of the app can detect the first one
    daemon_threads = True


def _origin_ok(origin):
    # Only accept the browser extension (or local tools with no Origin) — never web pages.
    return (not origin) or origin.startswith(("chrome-extension://", "moz-extension://", "extension://"))


def make_server(inbox, capture=lambda: True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            origin = self.headers.get("Origin")
            if origin and _origin_ok(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            origin = self.headers.get("Origin", "")
            if not _origin_ok(origin):
                return self._send(403, {})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin or "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/ping"):
                return self._send(200, {"app": "DMTOR", "version": VERSION, "capture": bool(capture())})
            self._send(404, {})

        def do_POST(self):
            if not _origin_ok(self.headers.get("Origin", "")):
                return self._send(403, {"error": "forbidden"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            if self.path == "/show":
                inbox.put({"action": "show"})
                return self._send(200, {"ok": True})
            if self.path != "/add":
                return self._send(404, {})
            url = str(data.get("url", ""))
            ok = url.startswith(("http://", "https://"))
            if data.get("type") == "torrent":
                ok = ok or url.startswith("magnet:") or (
                    url.lower().endswith(".torrent") and os.path.isfile(url))
            if not ok:
                return self._send(400, {"error": "bad url"})
            inbox.put(data)
            self._send(200, {"ok": True})

    srv = _Server(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
