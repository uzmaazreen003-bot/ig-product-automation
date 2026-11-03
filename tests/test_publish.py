import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import mock_graph
srv = mock_graph.start(); base = f"http://127.0.0.1:{srv.server_port}"
os.environ.update(GRAPH_BASE=base, RUPLOAD_BASE=base, PUBLISH_POLL_SLEEP="0.05", IG_ACCESS_TOKEN="TESTTOKEN")
from src import publish, main as m
S = mock_graph.STATE

def run(plan, **kw):
    S["calls"].clear(); S["polls"].clear()
    return publish.publish_plan(plan, "17841425701964826", "TESTTOKEN", **kw)

tmp = tempfile.mkdtemp(); vid = os.path.join(tmp, "v.mp4"); open(vid, "wb").write(b"x" * 5000)
reel = {"format": "reel", "caption": "cap", "files": [vid], "media_urls": [f"{base}/files/v.mp4"]}
# 1) resumable path
mid, link = run(reel)
kinds = [c[0] for c in S["calls"]]
assert mid == "MEDIA123" and "UPLOAD" in kinds, S["calls"]
up = [c for c in S["calls"] if c[0] == "UPLOAD"][0][2]; assert up == {"bytes": 5000, "auth": "OAuth ", "offset": "0"}, up
first_post = [c for c in S["calls"] if c[0] == "POST"][0][2]
assert first_post["media_type"] == "REELS" and first_post["upload_type"] == "resumable" and first_post["share_to_feed"] == "true"
print("reel resumable OK ->", link)
# 2) resumable fails -> fallback to video_url
S["fail_resumable"] = True
mid, _ = run(reel)
posts = [c[2] for c in S["calls"] if c[0] == "POST" and c[1].endswith("/media")]
assert posts[-1].get("video_url", "").endswith("v.mp4"), posts
print("reel fallback to video_url OK")
S["fail_resumable"] = False
# 3) carousel
imgs = [f"{base}/files/{i}.jpg" for i in range(3)]
car = {"format": "carousel", "caption": "cap", "files": [], "media_urls": imgs}
mid, _ = run(car)
posts = [c[2] for c in S["calls"] if c[0] == "POST" and c[1].endswith("/media")]
assert sum(1 for p in posts if p.get("is_carousel_item") == "true") == 3
assert posts[-1]["media_type"] == "CAROUSEL" and posts[-1]["children"].count(",") == 2
print("carousel OK")
# 4) bad token is classified, no retries storm
S["bad_token"] = True
try:
    run(car); raise SystemExit("should have failed")
except publish.PublishError as e:
    assert e.kind == "token", e.kind
print("token error classified OK")
shutil.rmtree(tmp)
