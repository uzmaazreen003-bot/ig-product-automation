"""Reels in the 'studio' style: 2D motion graphics + hand-drawn doodles + anime presenter + voice-over + natural SFX.

Everything on screen and in the voice-over comes from data/products.json (no AI-written text), so nothing can be invented.
If anything fails, main.py falls back to the older motion Reel.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.join(HERE, "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)

import common  # noqa: E402
import render as srender  # noqa: E402
import sfx  # noqa: E402
import timeline  # noqa: E402

THEMES = [
    (("breakup", "overthink", "why trap", "closure", "healing", "anxiety", "mind"), ["thought", "brain", "moon", "heart", "hourglass", "bulb"], "thought"),
    (("money", "budget", "salary", "saving", "finance", "debt", "expense"), ["wallet", "piggy", "chart", "calendar", "shield", "bank"], "wallet"),
    (("ebook", "sell", "business", "income", "ai", "freelanc", "blog", "side hustle"), ["laptop", "bulb", "chart", "notepad", "target", "gift"], "laptop"),
    (("self-care", "selfcare", "self care", "journal", "gratitude", "wellness", "routine", "habit"), ["leaf", "cup", "bed", "sun", "heart", "book"], "leaf"),
    (("planner", "schedule", "calendar", "organi", "to-do", "productiv"), ["calendar", "notepad", "alarm", "target", "check", "clock"], "calendar"),
]
DEFAULT_THEME = (("",), ["book", "star", "bulb", "check", "sparkle", "heart"], "book")


def theme_for(p):
    text = " ".join([p.get("title", ""), p.get("subtitle", "")] + list(p.get("tags", []))).lower()
    for keys, icons, main in THEMES:
        if any(k in text for k in keys):
            return icons, main
    return DEFAULT_THEME[1], DEFAULT_THEME[2]


def _short(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def _item_text(s, maxw=10):
    s = str(s).split(":")[0].strip()
    w = s.split()[:maxw]
    while len(w) > 3 and w[-1].lower().strip(",;") in ("and", "or", "with", "a", "the", "of", "to", "for", "in", "on", "an"):
        w.pop()
    return " ".join(w).rstrip(",;")


def _cue(text):
    for w in text.lower().split():
        w = re.sub(r"[^a-z0-9]", "", w)
        if len(w) > 3:
            return w
    return ""


def _scene(en, takeaway, v):
    en = re.sub(r"\s+", " ", en).strip()
    t = en.split()
    return dict(en=en, hi=en, en_tokens=t, hi_tokens=t, takeaway=takeaway, v=v)


def build_scenes(product, nth, cfg, cover):
    icons, main = theme_for(product)
    pr_word = (cfg.get("voice") or {}).get("price_word", "rupees")
    sym = cfg.get("currency_symbol", "₹")
    hooks = product["hooks"]
    hook = hooks[nth % len(hooks)]
    out = []
    # 1 hook
    if len(hook) <= 95:
        v1 = dict(type="quote", text=hook, by="")
    else:
        first = re.split(r"(?<=[.?!])\s", hook)[0]
        v1 = dict(type="doodle_big", heading="Sound familiar?", doodle=main, extras=icons[1:3], sub=_short(first, 70))
    out.append(_scene(hook, "Sound familiar?", v1))
    # 2 product
    sub = product.get("subtitle", "")
    out.append(_scene(f"Meet {product['title']}. {sub}." if sub else f"Meet {product['title']}.", product["title"],
                      dict(type="cover", title=product["title"], sub=_short(sub, 90), price=f"{sym}{product['price']}", _img=cover)))
    # 3 what's inside
    pts = [_item_text(p) for p in product["points"][:3]]
    items = [dict(text=t, cue=_cue(t), icon=icons[i % len(icons)]) for i, t in enumerate(pts)]
    out.append(_scene("Inside, you get: " + ". ".join(pts) + ".", "What's inside",
                      dict(type="bullets", heading="What's inside", items=items)))
    # 4 audience
    aud = [_item_text(a, 9) for a in product.get("audience", [])[:3]]
    if len(aud) >= 2:
        title = (product.get("audience_title") or "This is for you if").rstrip(":")
        items = [dict(text=t, cue=_cue(t), icon=None) for t in aud]
        out.append(_scene(title + ": " + ". ".join(aud) + ".", "Is this you?",
                          dict(type="checklist", heading=_short(title, 30), items=items)))
    # 5 price
    price = product["price"]
    meta = product.get("meta", "")
    out.append(_scene(f"All of this for just {price} {pr_word}, as an instant download.", f"Only {sym}{price}",
                      dict(type="big_number", label="Instant download", value=float(price), prefix=sym, suffix="", sub=_short(meta, 50), icon="coin")))
    # 6 CTA
    cta = (cfg.get("voice") or {}).get("cta", "Link in bio.")
    cta_items = [dict(text=_short(_item_text(p), 38), cue="", icon=None) for p in product["points"][:3]]
    out.append(_scene(f"Tap the link in bio and grab your copy today. {cta}".replace("Link in bio. Link in bio.", "Link in bio."),
                      "Link in bio",
                      dict(type="cta", product=product["id"], items=cta_items, badge="PDF · instant download", btn_text="Link in bio",
                           _product=dict(title=product["title"], price=f"{sym}{price}"))))
    return out


# ------------------------------------------------------------------ voice
async def _tts(text, voice, rate, path):
    import edge_tts
    try:
        com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(text, voice, rate=rate)
    ev = []
    with open(path, "wb") as fh:
        async for ch in com.stream():
            if ch["type"] == "audio":
                fh.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                off, dur = ch["offset"] / 1e7, ch["duration"] / 1e7
                ev.append((ch.get("text", ""), off, off + dur))
    return ev


def _fake(text, path):
    n = max(1.5, len(text.split()) * 0.36)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * n))
    return []


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def narrate(scenes, cfg, workdir):
    vc = cfg.get("voice") or {}
    voice, rate = vc.get("voice", "en-IN-NeerjaNeural"), vc.get("rate", "+0%")
    durs, evs = [], []
    for i, sc in enumerate(scenes):
        if os.environ.get("STUDIO_FAKE_TTS"):
            path = os.path.join(workdir, f"v{i}.wav")
            ev = _fake(sc["en"], path)
        else:
            path = os.path.join(workdir, f"v{i}.mp3")
            last = None
            for attempt in range(4):
                try:
                    ev = asyncio.run(_tts(sc["en"], voice, rate, path))
                    if os.path.getsize(path) > 2000:
                        break
                    last = "empty audio"
                except Exception as exc:  # noqa: BLE001
                    last = exc
                time.sleep(3 * (attempt + 1))
            else:
                raise RuntimeError(f"voice failed: {last}")
        sc["audio"] = path
        durs.append(_duration(path))
        evs.append(ev)
    return durs, evs


# ------------------------------------------------------------------ main entry
LAST = {}
PILL = {"thought": "overthinking", "wallet": "money", "leaf": "selfcare", "calendar": "mental_load"}


def _hindi_reel(product, nth, cfg, cover, out_path, workdir):
    import llm
    import tts
    sym = cfg.get("currency_symbol", "₹")
    short = [_short(_item_text(p), 38) for p in product.get("points", [])[:3]]
    pcfg = dict(products={product["id"]: dict(title=product["title"], tagline=product.get("subtitle", ""), benefits=short,
                                              price=f"{sym}{product['price']}", link=product["url"])})
    res = llm.make_ig_short(product, nth, pcfg)
    scs = res["scenes"]
    last = scs[-1]
    if cover is not None:
        last["v"] = dict(type="cover", title=product["title"], sub=_short(product.get("subtitle", ""), 90),
                         price=f"{sym}{product['price']}", btn="Link in bio", _img=cover)
    else:
        last["v"]["btn_text"] = "Link in bio"
        last["v"]["badge"] = "PDF · instant download"
    _, main = theme_for(product)
    palette = common.PALETTE_ORDER[sum(ord(c) for c in product["id"]) % len(common.PALETTE_ORDER)]
    plan = dict(format="short", palette=palette, pillar=PILL.get(main, "product"), link_text="Link in bio",
                pill_text="Roz naye tips • Follow", scenes=scs)
    hc = cfg.get("studio_hi", {})

    def run(engine):
        durs, evs = [], []
        for i, sc in enumerate(scs):
            path = os.path.join(workdir, f"h{engine}{i}.mp3")
            if os.environ.get("STUDIO_FAKE_TTS"):
                path = path.replace(".mp3", ".wav")
                evs.append(_fake(sc["hi"], path))
            elif engine == "gemini":
                evs.append(tts.synth_gemini(sc["hi"], hc.get("gemini_voice", "Leda"), hc.get("gemini_tts_models", ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]),
                                            hc["voice_style"], path))
                time.sleep(6)
            else:
                evs.append(tts.synth(sc["hi"], hc.get("edge_voice", "hi-IN-SwaraNeural"), hc.get("edge_rate", "+0%"), path))
                time.sleep(0.3)
            sc["audio"] = path
            durs.append(tts.duration(path))
        return durs, evs

    try:
        durs, evs = run("gemini")
    except Exception as exc:  # noqa: BLE001
        print(f"[reel] Gemini voice failed ({exc}); using the edge voice for the WHOLE reel")
        durs, evs = run("edge")
    voice_items, events = timeline.build(plan, durs, evs)
    wav = os.path.join(workdir, "mix.wav")
    sfx.mix_audio(voice_items, events, plan["total"], wav)
    srender.render_video(plan, cfg, wav, out_path)
    from . import content
    short_url = product["url"].replace("https://", "")
    lines = [scs[0]["en"], "", product["title"] + (f": {product['subtitle']}" if product.get("subtitle") else ""), ""]
    if cfg.get("show_price", True):
        lines.append("🛒 " + " · ".join(x for x in [f"{sym}{product['price']}", product.get("meta")] if x))
    lines.append(f"🔗 Link in bio · {short_url}")
    if product.get("disclaimer"):
        lines += ["", product["disclaimer"]]
    lines += ["", " ".join(content.clean_hashtags(product.get("tags", []), cfg))]
    LAST["caption"] = "\n".join(lines)[:2150]
    print(f"[reel] studio style (Hindi tips + product pitch); palette {palette}; length {plan['total']:.1f}s; {len(scs)} scenes")
    return out_path


def make_reel(product, nth, cfg, cover, out_path, workdir):
    LAST.clear()
    if (cfg.get("studio_hi") or {}).get("enabled") and os.environ.get("GEMINI_API_KEY"):
        try:
            return _hindi_reel(product, nth, cfg, cover, out_path, workdir)
        except Exception as exc:  # noqa: BLE001
            print(f"[reel] Hindi tips style failed ({exc!r}); using the English product Reel instead")
            LAST.clear()
    scs = build_scenes(product, nth, cfg, cover)
    palette = common.PALETTE_ORDER[sum(ord(c) for c in product["id"]) % len(common.PALETTE_ORDER)]
    plan = dict(format="short", palette=palette, pillar="product", link_text="Link in bio", pill_text="Follow for more guides", scenes=scs)
    durs, evs = narrate(scs, cfg, workdir)
    voice_items, events = timeline.build(plan, durs, evs)
    wav = os.path.join(workdir, "mix.wav")
    sfx.mix_audio(voice_items, events, plan["total"], wav)
    srender.render_video(plan, cfg, wav, out_path)
    print(f"[reel] studio style; palette {palette}; length {plan['total']:.1f}s; {len(scs)} scenes")
    return out_path
