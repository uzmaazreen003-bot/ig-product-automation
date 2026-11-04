from datetime import datetime
from src import content
cfg = {"daily_slots": [{"time": "19:00", "format": "reel"}, {"time": "20:30", "format": "carousel"}]}
T = lambda h, m: datetime(2026, 11, 4, h, m)
H = lambda *fs: [{"date": "2026-11-04", "format": f, "status": "published"} for f in fs]
assert content.due_format([], cfg, T(18, 59)) is None
assert content.due_format([], cfg, T(19, 5)) == "reel"
assert content.due_format(H("reel"), cfg, T(19, 40)) is None
assert content.due_format(H("reel"), cfg, T(20, 31)) == "carousel"
assert content.due_format([], cfg, T(20, 35)) == "reel"            # missed reel is made up first
assert content.due_format(H("reel"), cfg, T(22, 0)) == "carousel"  # backup run
assert content.due_format(H("reel", "carousel"), cfg, T(22, 0)) is None
assert content.due_format([{"date": "2026-11-04", "format": "reel", "status": "failed"}], cfg, T(19, 5)) == "reel"
print("slots OK")
