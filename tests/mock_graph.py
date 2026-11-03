"""Tiny fake of the Instagram Graph API for offline tests."""
import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {"calls": [], "fail_resumable": False, "bad_token": False, "n": 0, "polls": {}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length", 0)); return self.rfile.read(n)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        STATE["calls"].append(("GET", u.path, {k: v[0] for k, v in q.items() if k != "access_token"}))
        if u.path.startswith("/files/"):
            self.send_response(200); self.end_headers(); return
        if STATE["bad_token"]:
            return self._send(400, {"error": {"message": "Invalid OAuth access token", "code": 190}})
        if u.path.endswith("/content_publishing_limit"):
            return self._send(200, {"data": [{"quota_usage": 0}]})
        if u.path.endswith("/media_files/x.jpg") or u.path.startswith("/files/"):
            self.send_response(200); self.end_headers(); return
        cid = u.path.strip("/")
        if "fields" in q and "status_code" in q["fields"][0]:
            STATE["polls"][cid] = STATE["polls"].get(cid, 0) + 1
            return self._send(200, {"status_code": "IN_PROGRESS" if STATE["polls"][cid] < 2 else "FINISHED"})
        if "permalink" in q.get("fields", [""])[0]:
            return self._send(200, {"permalink": "https://www.instagram.com/reel/TEST/"})
        return self._send(200, {"username": "uzmaazreen.studio", "media_count": 3})
    def do_POST(self):
        u = urlparse(self.path); body = self._body()
        if u.path.startswith("/ig-api-upload"):
            STATE["calls"].append(("UPLOAD", u.path, {"bytes": len(body), "auth": self.headers.get("Authorization", "")[:6], "offset": self.headers.get("offset")}))
            if STATE["fail_resumable"]:
                return self._send(500, {"error": {"message": "upload broke", "code": 1}})
            return self._send(200, {"success": True})
        form = {k: v[0] for k, v in parse_qs(body.decode()).items() if k != "access_token"}
        STATE["calls"].append(("POST", u.path, form))
        if STATE["bad_token"]:
            return self._send(400, {"error": {"message": "Invalid OAuth access token", "code": 190}})
        STATE["n"] += 1
        if u.path.endswith("/media_publish"):
            return self._send(200, {"id": "MEDIA123"})
        out = {"id": f"C{STATE['n']}"}
        if form.get("upload_type") == "resumable":
            out["uri"] = f"http://127.0.0.1:{self.server.server_port}/ig-api-upload/v1/C{STATE['n']}"
        return self._send(200, out)

def start():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
