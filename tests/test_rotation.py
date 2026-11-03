import os, sys, json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import content
from src.main import load_json
cfg = load_json("config.json"); prods = load_json("products.json")
hist, start = [], datetime(2026, 11, 3, 19, 0, tzinfo=content.IST)
rows = []
for d in range(60):
    now = start + timedelta(days=d)
    date = now.strftime("%Y-%m-%d")
    assert not content.already_posted_on(hist, date)
    fmt = content.format_for(now, cfg)
    p = content.pick_product(prods, hist, cfg)
    angle = content.pick_angle(p, fmt, hist)
    hist.append(dict(date=date, product_id=p["id"], format=fmt, angle=angle, status="published"))
    assert content.already_posted_on(hist, date)
    rows.append((date, fmt, p["id"], angle))
ids = [r[2] for r in rows]
gap = min(len(ids[i+1:i+9]) and [j for j in range(i+1, len(ids)) if ids[j] == ids[i]][:1] or [99] for i in range(len(ids)-9)) if False else None
min_gap = min((j - i) for i in range(len(ids)) for j in range(i+1, len(ids)) if ids[j] == ids[i])
print("posts:", len(rows), "· distinct products:", len(set(ids)), "· min gap between repeats:", min_gap)
assert len(set(ids[:18])) == 18, "first 18 posts must cover every product once"
assert min_gap >= 9
from collections import Counter
print("formats:", dict(Counter(r[1] for r in rows)))
print("angles :", dict(Counter(r[3] for r in rows)))
# failed posts must not count as promoted
h2 = [dict(date="2026-11-03", product_id=prods[0]["id"], format="reel", angle="showcase", status="failed")]
assert content.pick_product(prods, h2, cfg)["id"] == prods[0]["id"], "failed post must not block retry of same product"
assert not content.already_posted_on(h2, "2026-11-03")
print("failed-post handling OK")
for r in rows[:8]: print(r)
