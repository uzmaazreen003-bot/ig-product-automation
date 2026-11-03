"""Voice-over path against a fake ElevenLabs server (no network, no key)."""
import http.server, json, os, subprocess, sys, tempfile, threading

tmp = tempfile.mkdtemp()
tone = os.path.join(tmp, "tone.mp3")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=3.2", tone], check=True)
TONE = open(tone, "rb").read()
SEEN = []

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
        SEEN.append((self.path, self.headers.get("xi-api-key"), body["text"]))
        if self.headers.get("xi-api-key") != "k":
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"detail":"bad key"}'); return
        self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.end_headers(); self.wfile.write(TONE)

srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"

def run(key):
    d = os.path.join(tmp, "data" + str(key)); o = os.path.join(tmp, "out" + str(key)); os.makedirs(d); os.makedirs(o)
    for f in ("config.json", "products.json"):
        open(os.path.join(d, f), "w").write(open(os.path.join("data", f)).read())
    open(os.path.join(d, "history.json"), "w").write("[]")
    env = dict(os.environ, IG_DATA_DIR=d, IG_OUT_DIR=o, ELEVENLABS_BASE=base, ELEVENLABS_API_KEY=key)
    r = subprocess.run([sys.executable, "-m", "src.main", "plan", "--format", "reel", "--product", "6fTMQ"], env=env, capture_output=True, text=True)
    print(r.stdout[-400:], r.stderr[-400:])
    mp4 = [f for f in os.listdir(o) if f.endswith(".mp4")]
    assert r.returncode == 0 and mp4, "plan failed"
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", os.path.join(o, mp4[0])], capture_output=True, text=True).stdout
    return p

good = run("k"); print("good key ->", good.split())
assert any("voice_id" in x[0] or "PUT_VOICE_ID_HERE" in x[0] for x in SEEN)
assert len(SEEN) == 6, len(SEEN)
for x in SEEN: print("  spoken:", x[2])
bad = run("wrong"); print("bad key -> silent reel still produced"); assert "audio" in bad
print("VOICE OK")
