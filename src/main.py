"""Entry point.

  python -m src.main plan     [--format auto|reel|carousel] [--product ID] [--force]
  python -m src.main publish
  python -m src.main check

`plan` picks the product, renders media into out/ and writes out/plan.json (never touches history).
`publish` posts out/plan.json to Instagram and records the result in data/history.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from . import content, motion, publish, render, voice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("IG_DATA_DIR") or os.path.join(ROOT, "data")
OUT = os.environ.get("IG_OUT_DIR") or os.path.join(ROOT, "out")

SCENE_SECONDS = {"hook": 2.8, "cover": 2.6, "point": 2.7, "cta": 3.4}


def load_json(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{k}={v}\n" for k, v in kv.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(lines)
    print("[output]", ", ".join(f"{k}={v}" for k, v in kv.items()))


def media_url(filename):
    base = os.environ.get("MEDIA_BASE_URL")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
        base = f"https://raw.githubusercontent.com/{repo}/media"
    return f"{base.rstrip('/')}/{filename}"


# ---------------------------------------------------------------- plan

def render_reel(product, script, pal, cover, cfg, stem, workdir):
    out = os.path.join(OUT, f"{stem}.mp4")
    if cfg.get("reel_style", "motion") == "motion":
        return render_reel_motion(product, script, pal, cover, cfg, stem, workdir, out)
    return render_reel_classic(product, script, pal, cover, cfg, stem, workdir, out)


def _voice(product, script, cfg, workdir, stem):
    if not voice.enabled(cfg):
        return None, None, "off"
    try:
        clips, chars = voice.make_clips(product, script, cfg, workdir, stem)
        return clips, [voice.duration(p) for p in clips], f"on ({chars} characters)"
    except voice.VoiceError as e:
        print(f"[voice] FAILED, Reel made without voice: {e}")
        return None, None, f"FAILED: {e}"


def render_reel_motion(product, script, pal, cover, cfg, stem, workdir, out):
    scenes = [motion.scene_hook(product, script["hook"], pal, cover, cfg), motion.scene_cover(product, pal, cover, cfg)]
    for i, item in enumerate(script["items"]):
        scenes.append(motion.scene_point(product, script["header"], item, i, len(script["items"]), pal, cover, cfg))
    scenes.append(motion.scene_cta(product, pal, cover, cfg))
    kinds = ["hook", "cover"] + ["point"] * len(script["items"]) + ["cta"]
    durs = [SCENE_SECONDS[k] + 0.2 for k in kinds]
    clips, clip_len, note = _voice(product, script, cfg, workdir, stem)
    if clip_len:
        durs = [max(d, c + 0.3 + 0.6) for d, c in zip(durs, clip_len)]
    total = sum(durs)
    starts = [sum(durs[:i]) for i in range(len(durs))]
    vo = [(starts[i] + 0.3, p) for i, p in enumerate(clips)] if clips else []
    wav = os.path.join(workdir, f"{stem}-audio.wav")
    motion.build_audio(motion.events_for(scenes, durs), vo, total, wav)
    motion.build_reel(scenes, durs, out, wav)
    print(f"[reel] motion style; voice {note}; length {total:.1f}s")
    return [out]


def render_reel_classic(product, script, pal, cover, cfg, stem, workdir, out):
    scenes, durs = [], []

    def add(img, kind, name):
        path = os.path.join(workdir, f"{stem}-{name}.png")
        render.save_png(img, path)
        scenes.append(path)
        durs.append(SCENE_SECONDS[kind])

    voice_clips, clip_len, voice_note = _voice(product, script, cfg, workdir, stem)
    add(render.scene_hook(product, script["hook"], pal, cover, cfg), "hook", "s1")
    add(render.scene_cover(product, pal, cover, cfg), "cover", "s2")
    for i, item in enumerate(script["items"]):
        add(render.scene_point(product, script["header"], item, i, len(script["items"]), pal, cover, cfg), "point", f"s{3 + i}")
    add(render.scene_cta(product, pal, cover, cfg), "cta", "s9")
    ambient = cfg.get("ambient_audio")
    ambient = os.path.join(ROOT, ambient) if ambient else None
    if clip_len:
        durs[:] = [max(d, c + 0.25 + 0.55) for d, c in zip(durs, clip_len)]
    render.build_reel(scenes, durs, out, ambient=ambient, voice_clips=voice_clips)
    print(f"[reel] classic style; voice {voice_note}; length {sum(durs):.1f}s")
    return [out]


def render_carousel(product, script, pal, cover, cfg, stem):
    files = []
    for i, (kind, header, items) in enumerate(script["slides"], start=1):
        if kind == "cover":
            img = render.slide_cover(product, script["hook"], pal, cover, cfg)
        elif kind == "list":
            img = render.slide_list(product, header, items, pal, cover, cfg)
        else:
            img = render.slide_cta(product, pal, cover, cfg)
        path = os.path.join(OUT, f"{stem}-{i}.jpg")
        render.save_jpeg(img, path)
        files.append(path)
    return files


def cmd_plan(args):
    cfg = load_json("config.json")
    products = load_json("products.json")
    history = load_json("history.json", [])
    now = content.now_ist()
    today = now.strftime("%Y-%m-%d")

    slots = cfg.get("daily_slots")
    if slots:
        if args.format != "auto":
            fmt = args.format                      # manual run: you chose the format
        elif args.force:
            fmt = slots[0]["format"]
        else:
            fmt = content.due_format(history, cfg, now)
            if not fmt:
                print(f"[plan] nothing due right now ({now.strftime('%H:%M')} IST); all of today's posts are done or not yet due")
                gh_output(skip="true")
                return 0
    else:
        if not args.force and content.already_posted_on(history, today):
            print(f"[plan] already published on {today} (IST); nothing to do")
            gh_output(skip="true")
            return 0
        fmt = args.format if args.format != "auto" else content.format_for(now, cfg)
    product = content.pick_product(products, history, cfg, args.product or None)
    angle = content.pick_angle(product, fmt, history)
    nth = content.times_promoted(product, history)
    pal = render.palette_for(product["id"])

    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        os.remove(os.path.join(OUT, old)) if os.path.isfile(os.path.join(OUT, old)) else None

    cover = render.load_cover(product, os.path.join(OUT, ".cache"))
    stem = f"{today}-{product['id']}-{fmt}-{angle}"
    print(f"[plan] {today} {fmt} · product {product['id']} ({product['title']}) · angle {angle} · cover={'yes' if cover else 'no'}")

    if fmt == "reel":
        script = content.reel_script(product, angle, nth)
        with tempfile.TemporaryDirectory() as tmp:
            files = render_reel(product, script, pal, cover, cfg, stem, tmp)
    else:
        script = content.carousel_script(product, angle, nth)
        files = render_carousel(product, script, pal, cover, cfg, stem)

    caption = content.build_caption(product, angle, script, cfg, fmt)
    plan = {
        "date": today,
        "time_ist": now.strftime("%H:%M"),
        "product_id": product["id"],
        "product_title": product["title"],
        "format": fmt,
        "angle": angle,
        "caption": caption,
        "files": files,
        "media_urls": [media_url(os.path.basename(f)) for f in files],
    }
    save_json(os.path.join(OUT, "plan.json"), plan)
    with open(os.path.join(OUT, "caption.txt"), "w", encoding="utf-8") as fh:
        fh.write(caption + "\n")
    gh_output(skip="false", format=fmt, product=product["id"])
    print("---- caption ----")
    print(caption)
    return 0


# ---------------------------------------------------------------- publish

def cmd_publish(args):
    cfg = load_json("config.json")
    history = load_json("history.json", [])
    with open(os.path.join(OUT, "plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        write_error("The GitHub secret IG_ACCESS_TOKEN is missing or empty.")
        return 1

    entry = {k: plan[k] for k in ("date", "time_ist", "product_id", "product_title", "format", "angle")}
    try:
        media_id, permalink = publish.publish_plan(plan, cfg["ig_user_id"], token, cfg.get("video_method", "auto"))
    except publish.PublishError as exc:
        entry.update(status="failed", error=f"{exc.kind}: {exc}")
        history.append(entry)
        save_json(os.path.join(DATA, "history.json"), history)
        hint = {
            "token": "The Instagram access token was rejected (expired, revoked or wrong). Generate a new token in the Meta app dashboard "
                     "(Instagram API setup → Generate token) and replace the IG_ACCESS_TOKEN secret.",
            "rate_limit": "Instagram's publishing limit was hit. The next scheduled run will try again.",
            "media_url": "Instagram could not download the media file from the repo's `media` branch.",
        }.get(exc.kind, "See the run log for details.")
        write_error(f"{exc}\n\n{hint}")
        print(f"[publish] FAILED: {exc}")
        return 1
    entry.update(status="published", media_id=media_id, permalink=permalink)
    history.append(entry)
    save_json(os.path.join(DATA, "history.json"), history)
    print(f"[publish] published {plan['format']} for {plan['product_id']}: {permalink or media_id}")
    return 0


def write_error(text):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "error.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


def cmd_check(args):
    cfg = load_json("config.json")
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        print("IG_ACCESS_TOKEN secret is empty or missing")
        return 1
    try:
        info = publish.call("GET", f"{publish.GRAPH}/{cfg['ig_user_id']}", token, params={"fields": "username,media_count"}, retries=1)
        used = publish.quota(cfg["ig_user_id"], token)
    except publish.PublishError as exc:
        print(f"Token check FAILED ({exc.kind}): {exc}")
        return 1
    print(f"OK: @{info.get('username')} · media_count={info.get('media_count')} · publishing quota used (24h)={used}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--format", default="auto", choices=["auto", "reel", "carousel"])
    p.add_argument("--product", default="")
    p.add_argument("--force", action="store_true")
    sub.add_parser("publish")
    sub.add_parser("check")
    args = ap.parse_args(argv)
    return {"plan": cmd_plan, "publish": cmd_publish, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
