"""Gemini (free tier) script writer: outline -> chapter scenes -> clean, validated scene plan."""
import json
import os
import re
import time

import requests

import scenes as S

API = "https://generativelanguage.googleapis.com/v1beta"
PREFERRED = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
_state = {"models": None, "good": None}

SYSTEM = (
    'Tum "Uzma Azreen Studio" ke Instagram Reels aur YouTube Shorts ki scriptwriter ho. '
    "Audience: India ki 18-35 saal ki ladkiyan aur mahilayein. Niche: Mind (overthinking, emotions), Money (budget, savings), "
    "Self-care aur ghar ke kaam ka mental load. Style: ek samajhdaar, warm, friendly 'didi' jo simple Hinglish mein baat karti hai. "
    "Chhote vakya, practical tips, relatable examples, koi lecture nahi. "
    "Rules: koi medical/financial/legal guarantee ya dava nahi; tone 'educational jaankari' ka; kisi ko darana ya sharminda nahi karna; "
    "fake statistics mat do (numbers sirf 'example' ke taur pe); kisi brand/celebrity ka naam mat lo; AI ya chatbot ka zikr mat karo; "
    "content original aur sach mein useful ho. BOLNE JAISI language: jaise koi dost baat kar rahi ho, kitab padhne jaisi nahi. "
    "Chhote vakya (8-14 words), beech beech mein natural words jaise 'अरे', 'सुनो', 'देखो', 'है ना?', 'सच बताऊँ तो', 'चलो'; "
    "sawal aur ! ka use, kahin kahin '...' se halka pause, ek-do jagah halka mazaak ya empathy (jaise 'पता है, ये सबके साथ होता है'). "
    "Har scene ka mood alag ho. Lecture ya formal bhasha bilkul nahi. Output hamesha valid JSON ho, aur kuch nahi."
)

NARRATION_RULES = """
Har scene ka format:
{"hi": "...", "en": "...", "takeaway": "...", "visual": {...}}
- "hi": narration Devanagari script mein (voice-over ke liye). English words bhi Devanagari mein likho (सैलरी, बजट, सेविंग्स, गोल). Numbers shabdon mein likho (पचास प्रतिशत, पच्चीस हज़ार रुपये). Vakya ke end mein । ? ! lagao.
- "en": wahi narration Roman Hinglish mein (screen captions ke liye). SAME order aur same words, ek Devanagari word = ek Roman word. Numbers yahan bhi shabdon mein ("pachaas percent").
- "takeaway": scene ka chhota key point, Roman Hinglish, max 5 words.
- "visual": niche ke types mein se EK object. Text bahut chhota rakho. Har scene mein alag type use karo (do baar lagataar same type nahi).

ZAROORI: screen par dikhne wala SAARA text (heading, items, labels, sub, takeaway) Roman Hinglish mein likho (jaise "Salary aate hi pehle savings"), poore English vakya BILKUL nahi (sirf aam English words jaise budget, list, plan chalenge).

Visual types (type field zaroori):
{"type":"title","heading":"max 6 words","sub":"max 12 words","icon":"star"}
{"type":"bullets","heading":"max 5 words","items":[{"text":"max 7 words","cue":"ek word jo narration mein tabhi bola jaye jab ye item dikhna chahiye"}]}   (2-4 items)
{"type":"steps","heading":"...","items":[{"text":"...","cue":"..."}]}   (3-4 items)
{"type":"checklist","heading":"...","items":[{"text":"...","cue":"..."}]}   (3-4 items)
{"type":"big_number","label":"max 8 words","value":5000,"prefix":"₹","suffix":"","sub":"max 8 words","icon":"coin"}
{"type":"split_bar","heading":"...","segments":[{"label":"Needs","pct":50,"note":"max 3 words","cue":"..."}]}   (2-4 segments, pct ka total 100)
{"type":"compare","heading":"...","left":{"title":"Galat","items":["max 6 words"]},"right":{"title":"Sahi","items":["max 6 words"]}}   (1-3 items each)
{"type":"bars","heading":"...","items":[{"label":"max 2 words","value":30,"prefix":"","suffix":"%","cue":"..."}]}   (3-5 items)
{"type":"quote","text":"max 18 words","by":"Uzma"}
{"type":"doodle_flow","heading":"max 5 words","items":[{"text":"max 3 words","icon":"<doodle>","cue":"..."}]}   (2-3 items; narration ki cheezon ko doodles ke arrows mein dikhata hai, jaise salary -> bank -> savings)
{"type":"doodle_big","heading":"max 5 words","doodle":"<doodle>","extras":["<doodle>","<doodle>"],"sub":"max 10 words"}   (ek bada doodle + 1-3 chhote)
Doodle/icon names (sirf inhi mein se): ICONLIST.
Zaroori: doodle_flow ya doodle_big kam se kam har 3rd scene mein use karo (jahan koi cheez/situation dikhai ja sakti ho), aur bullets/steps/checklist ke har item mein narration se milta hua "icon" bhi do.
"""

NARRATION_RULES = NARRATION_RULES.replace("ICONLIST", ", ".join(S.ICONS))

# ------------------------------------------------------------------ Gemini call
def _discover(key):
    """All text models this key can really use (so retired/unavailable names are skipped)."""
    try:
        r = requests.get(f"{API}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60)
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        bad = ("image", "tts", "live", "audio", "embed", "veo", "imagen", "robotics", "computer", "customtools", "gemma", "learnlm", "aqa")
        ok = [n for n in names if n.startswith("gemini") and not any(b in n for b in bad)]
        return ok
    except Exception as e:  # noqa: BLE001
        print("model discovery failed:", e)
        return []


def _rank(n):
    return ("lite" in n, "preview" in n or "exp" in n, "pro" in n and "flash" not in n, n)


def _extract_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


def ask(prompt, temperature=0.9, max_tokens=16384):
    """Try every usable model in turn; on 429/5xx move on (each model has its own quota); wait and repeat when all are busy."""
    key = os.environ["GEMINI_API_KEY"]
    if _state["models"] is None:
        print("LLM-RETRY-V3")
        found = _discover(key)
        env = os.environ.get("GEMINI_MODEL")
        pref = [m for m in PREFERRED if (not found or m in found)]
        rest = sorted([m for m in found if m not in pref], key=_rank)
        _state["models"] = ([env] if env else []) + pref + rest
        _state["models"] = list(dict.fromkeys(_state["models"]))
        _state["dead"] = set()
        print("  gemini models to try:", ", ".join(_state["models"][:10]))
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json",
                             "maxOutputTokens": max_tokens},
    }
    last_err = None
    waits = [20, 30, 45, 60, 90, 120, 150, 180]
    for cycle in range(len(waits) + 1):
        order = [m for m in _state["models"] if m not in _state["dead"]]
        if _state["good"] in order:
            order.remove(_state["good"])
            order.insert(0, _state["good"])
        for model in order:
            try:
                r = requests.post(f"{API}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json=body, timeout=240)
            except requests.RequestException as e:
                last_err = e
                continue
            if r.status_code in (400, 403, 404):
                last_err = f"{r.status_code} {r.text[:200]}"
                print(f"  gemini {model} not usable ({r.status_code})")
                _state["dead"].add(model)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"{r.status_code} {r.text[:200]}"
                print(f"  gemini {model}: {r.status_code}")
                if r.status_code == 429 and "PerDay" in r.text:
                    _state["dead"].add(model)
                time.sleep(2)
                continue
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                obj = _extract_json(text)
            except Exception as e:  # noqa: BLE001
                last_err = f"bad response: {e} {r.text[:200]}"
                print("  ", last_err[:160])
                continue
            _state["good"] = model
            return obj
        if cycle < len(waits):
            print(f"  all models busy, waiting {waits[cycle]}s (round {cycle + 1}/{len(waits)})")
            time.sleep(waits[cycle])
    raise RuntimeError(f"Gemini failed: {last_err}")


# ------------------------------------------------------------------ cleaning
def _s(x, n):
    return re.sub(r"\s+", " ", str(x if x is not None else "")).strip()[:n]


def _items(raw, lo, hi, tl=48):
    out = []
    for it in (raw or [])[:hi]:
        if isinstance(it, dict):
            t = _s(it.get("text"), tl)
            cue = _s(it.get("cue"), 20)
            icon = it.get("icon") if it.get("icon") in S.ICONS else None
        else:
            t, cue, icon = _s(it, tl), "", None
        if t:
            out.append(dict(text=t, cue=cue, icon=icon))
    return out if len(out) >= lo else []


def _num(x, default=None):
    try:
        return float(str(x).replace(",", "").replace("₹", "").replace("%", "").strip())
    except ValueError:
        return default


def clean_visual(v, takeaway, cfg, product_key):
    v = v if isinstance(v, dict) else {}
    ty = v.get("type")
    icon = v.get("icon") if v.get("icon") in S.ICONS else "sparkle"
    out = None
    if ty == "title" and _s(v.get("heading"), 70):
        out = dict(type="title", heading=_s(v["heading"], 70), sub=_s(v.get("sub"), 100), icon=icon)
    elif ty in ("bullets", "steps", "checklist"):
        items = _items(v.get("items"), 2, 5)
        if items:
            out = dict(type=ty, heading=_s(v.get("heading"), 44), items=items)
    elif ty == "big_number":
        val = _num(v.get("value"))
        out = dict(type="big_number", label=_s(v.get("label"), 60), value=val if val is not None else _s(v.get("value"), 14),
                   prefix=_s(v.get("prefix"), 2), suffix=_s(v.get("suffix"), 4), sub=_s(v.get("sub"), 70),
                   icon=v.get("icon") if v.get("icon") in S.ICONS else "coin")
    elif ty == "split_bar":
        segs = []
        for s in (v.get("segments") or [])[:4]:
            p = _num(s.get("pct") if isinstance(s, dict) else None)
            if isinstance(s, dict) and p and p > 0 and _s(s.get("label"), 14):
                segs.append(dict(label=_s(s["label"], 14), pct=p, note=_s(s.get("note"), 26), cue=_s(s.get("cue"), 20)))
        if len(segs) >= 2:
            out = dict(type="split_bar", heading=_s(v.get("heading"), 44), segments=segs)
    elif ty == "compare":
        try:
            l = [_s(i, 44) for i in v["left"]["items"][:3] if _s(i, 44)]
            r = [_s(i, 44) for i in v["right"]["items"][:3] if _s(i, 44)]
            if l and r:
                out = dict(type="compare", heading=_s(v.get("heading"), 44),
                           left=dict(title=_s(v["left"].get("title"), 14) or "Galat", items=l),
                           right=dict(title=_s(v["right"].get("title"), 14) or "Sahi", items=r))
        except (KeyError, TypeError, AttributeError):
            out = None
    elif ty == "bars":
        its = []
        for i in (v.get("items") or [])[:5]:
            val = _num(i.get("value")) if isinstance(i, dict) else None
            if isinstance(i, dict) and val and val > 0 and _s(i.get("label"), 20):
                its.append(dict(label=_s(i["label"], 20), value=val, prefix=_s(i.get("prefix"), 2),
                                suffix=_s(i.get("suffix"), 4), cue=_s(i.get("cue"), 20)))
        if len(its) >= 2:
            out = dict(type="bars", heading=_s(v.get("heading"), 44), items=its)
    elif ty == "quote" and _s(v.get("text"), 160):
        out = dict(type="quote", text=_s(v["text"], 160), by=_s(v.get("by"), 30))
    elif ty == "doodle_flow":
        its = []
        for i in (v.get("items") or [])[:3]:
            if isinstance(i, dict) and _s(i.get("text"), 30):
                its.append(dict(text=_s(i["text"], 30), icon=i.get("icon") if i.get("icon") in S.ICONS else "sparkle", cue=_s(i.get("cue"), 20)))
        if len(its) >= 2:
            out = dict(type="doodle_flow", heading=_s(v.get("heading"), 44), items=its)
    elif ty == "doodle_big":
        if v.get("doodle") in S.ICONS:
            out = dict(type="doodle_big", heading=_s(v.get("heading"), 44), doodle=v["doodle"],
                       extras=[e for e in (v.get("extras") or [])[:3] if e in S.ICONS], sub=_s(v.get("sub"), 70))
    elif ty == "cta":
        items = _items(v.get("items"), 1, 3, 38) or [dict(text=b, cue="", icon=None) for b in cfg["products"][product_key]["benefits"][:3]]
        out = dict(type="cta", product=product_key, items=items)
    if out is None:
        out = dict(type="quote", text=_s(takeaway, 100) or "Chhota kadam, bada fark", by="Uzma")
    if out["type"] == "cta":
        out["_product"] = cfg["products"][product_key]
    return out


def clean_scene(raw, cfg, product_key):
    if not isinstance(raw, dict):
        return None
    hi, en = _s(raw.get("hi"), 600), _s(raw.get("en"), 600)
    if len(hi.split()) < 3 or len(en.split()) < 3:
        return None
    take = _s(raw.get("takeaway"), 40)
    return dict(hi=hi, en=en, hi_tokens=hi.split(), en_tokens=en.split(), takeaway=take,
                v=clean_visual(raw.get("visual"), take, cfg, product_key))


def _scenes(obj, cfg, product_key):
    raw = obj.get("scenes") if isinstance(obj, dict) else None
    out = [clean_scene(r, cfg, product_key) for r in (raw or [])]
    return [s for s in out if s]


def _ask_scenes(prompt, min_n, cfg, product_key, temp=0.9):
    for _ in range(3):
        obj = ask(prompt, temperature=temp)
        sc = _scenes(obj, cfg, product_key)
        if len(sc) >= min_n:
            return sc, obj
        print("  too few valid scenes, retrying")
    raise RuntimeError("Gemini returned too few valid scenes")


def _types_hint(prev):
    last = prev[-1]["v"]["type"] if prev else ""
    return f'Pichle scene ka visual type "{last}" tha, usse alag use karo.' if last else ""


# ------------------------------------------------------------------ long video
def make_long(topic, cfg, product_key):
    n_ch = cfg.get("long_chapters", 8)
    pr = cfg["products"][product_key]
    outline = ask(
        f'Topic: {topic["topic"]}\nPillar: {topic["pillar"]}\n\n'
        f"Ek lambi YouTube video (8-9 minute) ka outline banao. JSON:\n"
        '{"title":"...","thumb_text":"...","chapters":[{"title":"...","idea":"..."}],"description_intro":"...","tags":["..."]}\n'
        f"Rules: title Hinglish, max 70 characters, curiosity + benefit, clickbait/jhoot nahi. thumb_text: max 4 words, CAPS, Hinglish hook. "
        f"EXACTLY {n_ch} chapters, logical order (problem -> samajh -> solutions -> practice). Chapter title max 5 words (Hinglish). "
        "idea = 1 vakya mein is chapter mein kya sikhana hai. description_intro = 2-3 vakya Hinglish. tags: 10-14 (Hinglish+English mix, # nahi lagana).",
        temperature=0.8)
    title = _s(outline.get("title"), 95) or _s(topic["topic"], 95)
    chapters = [c for c in outline.get("chapters", []) if isinstance(c, dict) and _s(c.get("title"), 40)][:n_ch]
    if len(chapters) < 5:
        raise RuntimeError("outline has too few chapters")
    all_scenes, ch_marks = [], []

    time.sleep(4)
    intro, _ = _ask_scenes(
        f'Video title: "{title}"\nTopic: {topic["topic"]}\nChapters: {[c["title"] for c in chapters]}\n\n'
        'Sirf intro ke EXACTLY 2 scenes likho, JSON {"scenes":[...]}.\n'
        "Scene 1: hook (max 28 words): ek relatable sawal ya situation, pehle 3 second mein dhyan kheenchne wala; visual type 'title'. "
        "Scene 2: 'is video mein kya milega' (35-45 words), visual type 'bullets' jisme chapters ke 3-4 chhote naam.\n" + NARRATION_RULES,
        2, cfg, product_key)
    ch_marks.append(dict(title="Intro", scene=0))
    all_scenes += intro[:2]

    for i, ch in enumerate(chapters):
        time.sleep(4)
        prev_take = [s["takeaway"] for s in all_scenes[-4:]]
        sc, _ = _ask_scenes(
            f'Video title: "{title}"\nTopic: {topic["topic"]}\nChapter {i + 1} of {len(chapters)}: "{ch["title"]}" - {ch.get("idea", "")}\n'
            f"Saare chapters: {[c['title'] for c in chapters]}\nPichle scenes ke takeaways (repeat mat karo): {prev_take}\n"
            f"{_types_hint(all_scenes)}\n\n"
            'Is chapter ke EXACTLY 3 scenes likho, JSON {"scenes":[...]}. Har scene ki narration 38-52 words. '
            "Pehla scene chapter ko naturally shuru kare (greeting nahi, 'chapter' shabd bhi nahi bolna), baaki practical tips/examples. "
            "Ek scene mein ek hi idea. Kam se kam ek scene mein concrete example (numbers sirf example ke taur pe).\n" + NARRATION_RULES,
            3, cfg, product_key)
        ch_marks.append(dict(title=_s(ch["title"], 40), scene=len(all_scenes)))
        all_scenes += sc[:3]

    time.sleep(4)
    disc = ("Ye sirf educational jaankari hai, financial advice nahi." if topic["pillar"] == "money"
            else "Agar pareshani bahut zyada ho to kisi counsellor ya apne bharose ke insaan se zaroor baat karo.")
    outro, _ = _ask_scenes(
        f'Video title: "{title}"\nTopic: {topic["topic"]}\nChapters: {[c["title"] for c in chapters]}\n\n'
        'Outro ke EXACTLY 2 scenes likho, JSON {"scenes":[...]}.\n'
        "Scene 1: recap (35-45 words) - visual type 'checklist' ya 'bullets' jisme 3 main takeaways.\n"
        f'Scene 2: CTA (40-50 words), visual {{"type":"cta","product":"{product_key}","items":[{{"text":"..."}}]}} (2-3 benefits). '
        f'Soft pitch karo: "{pr["title"]}" ({pr["tagline"]}), bolo "link description mein hai", subscribe karne aur ek sawal comment karne ko bolo, '
        f'aur ek halka disclaimer: "{disc}" (Hinglish mein).\n' + NARRATION_RULES,
        2, cfg, product_key)
    ch_marks.append(dict(title="Recap aur resources", scene=len(all_scenes)))
    all_scenes += outro[:2]
    _force_cta(all_scenes[-1], cfg, product_key)
    return dict(title=title, thumb_text=_s(outline.get("thumb_text"), 40).upper() or "DEKHO YE",
                intro=_s(outline.get("description_intro"), 400), tags=_tags(outline.get("tags")),
                scenes=all_scenes, chapters=ch_marks)


# ------------------------------------------------------------------ short
def make_short(topic, cfg, product_key):
    pr = cfg["products"][product_key]
    sc, obj = _ask_scenes(
        f'Topic: {topic["topic"]}\nPillar: {topic["pillar"]}\n\n'
        "Ek YouTube Short (40-55 second) likho: sirf EK chhoti, practical tip is topic se. JSON:\n"
        '{"title":"...","tags":["..."],"scenes":[...]}\n'
        "Rules: title Hinglish max 60 characters (hook, clickbait nahi). 6 ya 7 scenes, poori narration milake 100-125 words. "
        "Scene 1 hook: max 14 words, seedha sawal ya surprising baat. Beech ke scenes: tip + example. "
        f'Aakhri scene: "{pr["title"]}" ka halka ullekh aur "link bio aur description mein hai" bolna; visual type "cta" '
        f'(product "{product_key}", items 2-3).\n' + NARRATION_RULES,
        5, cfg, product_key)
    return dict(title=_s(obj.get("title"), 95) or _s(topic["topic"], 95), thumb_text="", intro="",
                tags=_tags(obj.get("tags")), scenes=_cta_last(sc[:8], cfg, product_key), chapters=[])


def _force_cta(sc, cfg, product_key):
    if sc["v"]["type"] != "cta":
        items = [dict(text=b, cue="", icon=None) for b in cfg["products"][product_key]["benefits"][:3]]
        sc["v"] = dict(type="cta", product=product_key, items=items, _product=cfg["products"][product_key])


def _cta_last(scs, cfg, product_key):
    _force_cta(scs[-1], cfg, product_key)
    return scs


def _tags(raw):
    out, total = [], 0
    for t in (raw or []):
        t = _s(t, 30).lstrip("#")
        if t and total + len(t) < 450:
            out.append(t)
            total += len(t) + 1
    return out[:15]


# ------------------------------------------------------------------ Instagram Reel (tip + soft product pitch)
ANGLES = ["ek practical tip", "ek common galti aur uska aasaan solution", "ek 2-minute ka chhota exercise",
          "ek myth vs reality", "ek 3-step mini routine", "ek sawal jo log khud se poochte hain aur uska jawab"]


def make_ig_short(product, nth, cfg):
    """One Hinglish Reel: a useful tip related to the product's topic, then a soft pitch built ONLY from the product facts."""
    pid = product["id"]
    angle = ANGLES[nth % len(ANGLES)]
    pts = "\n".join("- " + p for p in product.get("points", [])[:6])
    aud = "\n".join("- " + a for a in product.get("audience", [])[:4])
    sc, obj = _ask_scenes(
        f'Product: "{product["title"]}" - {product.get("subtitle", "")} (price Rs {product["price"]}, {product.get("meta", "")})\n'
        f"Product ke asli points (sirf inhi ka zikr kar sakti ho, kuch naya ya extra vaada mat karo):\n{pts}\n"
        f"Ye kinke liye hai:\n{aud}\n\n"
        f"Ek Instagram Reel (40-55 second) likho: pehle {angle}, jo is product ke topic se related ho aur akele mein bhi sach mein useful ho "
        "(product ke points ko copy mat karo, apni tip do). Phir aakhir mein product ka halka sa zikr.\n"
        'JSON: {"scenes":[...]}\n'
        "Rules: 6 ya 7 scenes, poori narration milake 100-125 words. Scene 1 hook: max 14 words, relatable sawal ya surprising baat. "
        "Beech ke scenes: tip + chhota example. Koi guarantee/result ka vaada nahi, koi medical/financial/therapy claim nahi. "
        f'Aakhri scene: "{product["title"]}" ka halka ullekh (product ke points mein se ek-do cheezein), aur "link bio mein hai" bolna; '
        f'visual type "cta" (product "{pid}", items 2-3).\n' + NARRATION_RULES,
        5, cfg, pid)
    return dict(scenes=_cta_last(sc[:8], cfg, pid), tags=_tags(obj.get("tags")))
