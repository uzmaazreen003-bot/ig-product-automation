import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import mock_graph
srv = mock_graph.start(); base = f"http://127.0.0.1:{srv.server_port}"
os.environ.update(GRAPH_BASE=base, RUPLOAD_BASE=base, PUBLISH_POLL_SLEEP="0.05", IG_ACCESS_TOKEN="TESTTOKEN",
                  IG_DATA_DIR="/tmp/e2e/data", IG_OUT_DIR="/tmp/e2e/out", MEDIA_BASE_URL=f"{base}/files",
                  GITHUB_OUTPUT="/tmp/e2e/gh_output.txt")
from src import main as m
hist = lambda: json.load(open("/tmp/e2e/data/history.json"))

assert m.main(["plan", "--format", "reel"]) == 0
assert m.main(["publish"]) == 0
h = hist(); assert len(h) == 1 and h[0]["status"] == "published" and h[0]["media_id"] == "MEDIA123", h
print("1) reel published + recorded:", h[0]["product_id"], h[0]["angle"], h[0]["permalink"])

# same day again -> skipped (second cron fallback must not double-post)
open("/tmp/e2e/gh_output.txt", "w").close()
assert m.main(["plan", "--format", "reel"]) == 0
assert "skip=true" in open("/tmp/e2e/gh_output.txt").read()
print("2) second run same day skipped OK")

# carousel next product with --force
assert m.main(["plan", "--format", "carousel", "--force"]) == 0
plan = json.load(open("/tmp/e2e/out/plan.json")); assert len(plan["files"]) >= 3 and plan["product_id"] != h[0]["product_id"]
assert m.main(["publish"]) == 0
assert len(hist()) == 2
print("3) carousel with", len(plan["files"]), "slides published, product", plan["product_id"])

# failure path: bad token -> failed entry + error.txt + exit 1
mock_graph.STATE["bad_token"] = True
assert m.main(["plan", "--format", "reel", "--force"]) == 0
rc = m.main(["publish"]); assert rc == 1
last = hist()[-1]; assert last["status"] == "failed" and "token" in last["error"], last
err = open("/tmp/e2e/out/error.txt").read(); assert "IG_ACCESS_TOKEN" in err
print("4) token failure recorded + readable error written")
# the failed product is retried next (not skipped)
mock_graph.STATE["bad_token"] = False
assert m.main(["plan", "--format", "reel", "--force"]) == 0
assert json.load(open("/tmp/e2e/out/plan.json"))["product_id"] == last["product_id"]
print("5) failed product is retried next run")
assert m.main(["check"]) == 0
