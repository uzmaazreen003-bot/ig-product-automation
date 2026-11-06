"""Motion-graphics scene templates. Each template has prep() (reveal timing + sfx) and draw()."""
import math

import doodles
from PIL import Image, ImageFilter
from common import S2, clamp, ease_out, inr, mix, pop, prog, star_pts

BASE_ICONS = ["coin", "heart", "bulb", "check", "star", "lock", "target", "leaf", "moon", "clock", "book", "sparkle"]
ICONS = BASE_ICONS + [n for n in doodles.NAMES if n not in BASE_ICONS]
TYPES = ["title", "bullets", "steps", "checklist", "big_number", "split_bar", "compare", "bars", "quote", "cta", "doodle_flow", "doodle_big", "cover"]


# ------------------------------------------------------------------ helpers
def _n(s):
    return "".join(c for c in str(s).lower() if c.isalnum())


def cue_time(sc, cue):
    c = _n(cue or "")
    if len(c) < 3:
        return None
    for w, a, _b in sc["wt"]:
        x = _n(w)
        if len(x) >= 3 and (x.startswith(c) or c.startswith(x)):
            return max(0.6, sc["lead"] + a - 0.12)
    return None


def item_times(sc, n, cues, tl):
    lo = 0.9
    hi = max(lo + 0.5, tl - 1.0)
    out = []
    for i in range(n):
        ct = cue_time(sc, cues[i]) if i < len(cues) else None
        out.append(ct if ct is not None else lo + (hi - lo) * i / max(1, n))
    for i in range(1, n):
        out[i] = max(out[i], out[i - 1] + 0.4)
    return [min(max(x, 0.6), max(0.7, tl - 0.4)) for x in out]


def typed_lines(ctx, lines, n, cx, y_top, size, font, col, lh, align="mm"):
    """Draw lines with only the first n characters revealed (layout stays stable)."""
    rem = n
    for i, ln in enumerate(lines):
        full_w = ctx.tw(ln, size, font)
        x = cx - full_w / 2
        part = ln[: max(0, min(len(ln), rem))]
        rem -= len(ln) + 1
        if part:
            ctx.text(x, y_top + i * lh + lh / 2, part, size, col, font, "lm")


def wrap(ctx, text, size, font, maxw):
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and ctx.tw(t, size, font) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def fit(ctx, text, size, font, maxw, maxlines):
    s = size
    lines = wrap(ctx, text, s, font, maxw)
    for _ in range(14):
        lines = wrap(ctx, text, s, font, maxw)
        if len(lines) <= maxlines and all(ctx.tw(l, s, font) <= maxw * 1.02 for l in lines):
            return lines, s
        s *= 0.92
    return lines[:maxlines], s


def head(ctx, v, t, R):
    """Typed heading + accent underline. Returns bottom y."""
    k = ctx.k
    h = str(v.get("heading", ""))
    if not h:
        return ctx.h * 0.06
    lines, sz = fit(ctx, h, 36 * k, "Bold", ctx.w * 0.9, 2)
    lh = sz * 1.22
    y_top = ctx.h * 0.06
    n = int(max(0, t - R["h0"]) * R["cps"])
    typed_lines(ctx, lines, n, ctx.w / 2, y_top, sz, "Bold", ctx.th.ink, lh)
    total = sum(len(l) + 1 for l in lines)
    bottom = y_top + lh * len(lines)
    if n < total or t < R["h0"] + total / R["cps"] + 0.8:
        if int(t * 2.6) % 2 == 0:
            last = lines[min(len(lines) - 1, max(0, _line_of(lines, n)))]
            shown = last[: max(0, n - sum(len(l) + 1 for l in lines[:_line_of(lines, n)]))]
            x = ctx.w / 2 - ctx.tw(last, sz, "Bold") / 2 + ctx.tw(shown, sz, "Bold") + 5 * k
            yy = y_top + _line_of(lines, n) * lh + lh / 2
            ctx.rr(x, yy - sz * 0.5, x + 4 * k, yy + sz * 0.5, 2, fill=ctx.th.accent)
    g = ease_out((t - R["h0"] - total / R["cps"]) / 0.3)
    if g > 0:
        half = 46 * k * g
        ctx.rr(ctx.w / 2 - half, bottom + 4 * k, ctx.w / 2 + half, bottom + 9 * k, 3, fill=ctx.th.accent)
    return bottom + 14 * k


def _line_of(lines, n):
    c = 0
    for i, l in enumerate(lines):
        c += len(l) + 1
        if n < c:
            return i
    return len(lines) - 1


def head_prep(v, R, ev):
    h = str(v.get("heading", ""))
    R["h0"] = 0.35
    R["cps"] = max(14.0, len(h) / 1.0)
    n = min(len(h), 14)
    dur = len(h) / R["cps"]
    for i in range(n):
        ev.append((0.35 + dur * i / max(1, n), "key", 0.9))
    return 0.35 + dur


# ------------------------------------------------------------------ icons
def icon(ctx, name, cx, cy, r, col, bg=None):
    if r < 1:
        return
    if bg is not None:
        ctx.circle(cx, cy, r, fill=bg)
    if name in doodles.LIB:
        doodles.draw(ctx, name, cx, cy, r * 0.72, 1.0, col if col != bg else None)
        return
    g = r * 0.56
    if name == "coin":
        ctx.circle(cx, cy, g * 1.1, fill=col)
        ctx.text(cx, cy + g * 0.04, "₹", g * 1.5, bg or (255, 255, 255), "Bold")
    elif name == "heart":
        ctx.circle(cx - g * 0.5, cy - g * 0.25, g * 0.55, fill=col)
        ctx.circle(cx + g * 0.5, cy - g * 0.25, g * 0.55, fill=col)
        ctx.poly([(cx - g * 1.02, cy - g * 0.05), (cx + g * 1.02, cy - g * 0.05), (cx, cy + g * 1.1)], col)
    elif name == "bulb":
        ctx.circle(cx, cy - g * 0.2, g * 0.8, fill=col)
        ctx.rr(cx - g * 0.35, cy + g * 0.5, cx + g * 0.35, cy + g * 1.0, 2, fill=col)
    elif name == "check":
        ctx.line([(cx - g * 0.8, cy + g * 0.05), (cx - g * 0.2, cy + g * 0.65), (cx + g * 0.85, cy - g * 0.6)],
                 col, g * 0.38)
    elif name == "star":
        ctx.poly(star_pts(cx, cy + g * 0.05, g * 1.1, 5, 0.45), col)
    elif name == "lock":
        ctx.rr(cx - g * 0.8, cy - g * 0.1, cx + g * 0.8, cy + g * 0.95, 3, fill=col)
        ctx.arc((cx - g * 0.5, cy - g * 0.95, cx + g * 0.5, cy + g * 0.2), 180, 360, col, g * 0.28)
    elif name == "target":
        ctx.circle(cx, cy, g * 1.0, outline=col, width=g * 0.22)
        ctx.circle(cx, cy, g * 0.55, outline=col, width=g * 0.22)
        ctx.circle(cx, cy, g * 0.2, fill=col)
    elif name == "leaf":
        ctx.poly([(cx - g, cy + g * 0.9), (cx - g * 0.6, cy - g * 0.5), (cx + g * 0.2, cy - g * 1.0),
                  (cx + g, cy - g * 0.9), (cx + g * 0.8, cy + g * 0.0), (cx + g * 0.1, cy + g * 0.8)], col)
    elif name == "moon":
        ctx.circle(cx, cy, g * 1.0, fill=col)
        ctx.circle(cx + g * 0.5, cy - g * 0.35, g * 0.85, fill=bg or (255, 255, 255))
    elif name == "clock":
        ctx.circle(cx, cy, g * 1.0, outline=col, width=g * 0.22)
        ctx.line([(cx, cy), (cx, cy - g * 0.6)], col, g * 0.2)
        ctx.line([(cx, cy), (cx + g * 0.45, cy + g * 0.2)], col, g * 0.2)
    elif name == "book":
        ctx.rr(cx - g * 1.0, cy - g * 0.7, cx - g * 0.05, cy + g * 0.8, 3, fill=col)
        ctx.rr(cx + g * 0.05, cy - g * 0.7, cx + g * 1.0, cy + g * 0.8, 3, fill=col)
    else:  # sparkle
        ctx.poly(star_pts(cx, cy, g * 1.2, 4, 0.22), col)


def badge(ctx, cx, cy, r, text_or_icon, th, color, bg):
    ctx.circle(cx, cy, r, fill=bg)
    if text_or_icon in ICONS:
        icon(ctx, text_or_icon, cx, cy, r, color)
    else:
        ctx.text(cx, cy + r * 0.04, text_or_icon, r * 1.0, color, "Bold")


# ------------------------------------------------------------------ prep
def prep(sc, tl):
    v = sc["v"]
    ty = v["type"]
    R, ev = {}, []
    if ty == "title":
        end = head_prep(v, R, ev)
        R["sub"] = end + 0.3
        ev.append((0.2, "pop", 0.8))
        ev.append((R["sub"], "pop2", 0.6))
    elif ty in ("bullets", "steps", "checklist"):
        head_prep(v, R, ev)
        items = v["items"]
        R["it"] = item_times(sc, len(items), [i.get("cue") for i in items], tl)
        for t in R["it"]:
            ev.append((t, "ding" if ty == "checklist" else "pop", 0.8))
    elif ty == "big_number":
        R["n0"], R["n1"] = 0.7, 2.1
        ev.append((0.3, "pop", 0.8))
        for i in range(10):
            ev.append((R["n0"] + (R["n1"] - R["n0"]) * i / 10, "tick", 1.0))
        ev.append((R["n1"], "coin", 0.9))
    elif ty == "split_bar":
        head_prep(v, R, ev)
        segs = v["segments"]
        R["it"] = item_times(sc, len(segs), [s.get("cue") for s in segs], tl)
        for t in R["it"]:
            ev.append((t, "pop", 0.9))
            ev.append((t + 0.45, "pop2", 0.5))
    elif ty == "compare":
        head_prep(v, R, ev)
        m = max(len(v["left"]["items"]), len(v["right"]["items"]))
        ts = item_times(sc, m * 2, [], tl)
        R["l"] = ts[0::2]
        R["r"] = ts[1::2]
        for t in ts:
            ev.append((t, "pop", 0.7))
    elif ty == "bars":
        head_prep(v, R, ev)
        items = v["items"]
        R["it"] = item_times(sc, len(items), [i.get("cue") for i in items], tl)
        for t in R["it"]:
            ev.append((t, "pop", 0.8))
    elif ty == "cover":
        R["c0"] = 0.25
        R["t0"] = 0.9
        R["pr"] = 1.6
        ev.append((0.25, "pop", 0.9))
        ev.append((0.9, "pop2", 0.6))
        ev.append((1.6, "coin", 0.7))
    elif ty == "doodle_flow":
        head_prep(v, R, ev)
        items = v["items"]
        R["it"] = item_times(sc, len(items), [i.get("cue") for i in items], tl)
        for t in R["it"]:
            ev.append((t, "pop", 0.8))
            ev.append((t + 0.35, "tick", 0.7))
    elif ty == "doodle_big":
        head_prep(v, R, ev)
        R["d0"] = 0.9
        ev.append((0.9, "pop", 0.8))
        for j in range(len(v.get("extras", []))):
            ev.append((1.9 + 0.35 * j, "pop2", 0.6))
        R["cap"] = 2.2
    elif ty == "quote":
        R["q0"] = 0.4
        ev.append((0.4, "pop", 0.8))
    elif ty == "cta":
        R["card"] = 0.3
        ev.append((0.3, "pop", 0.9))
        items = v["items"]
        R["it"] = item_times(sc, len(items), [], tl)
        for t in R["it"]:
            ev.append((t, "ding", 0.7))
        bt = cue_time(sc, "link") or max(1.5, tl - 1.6)
        R["btn"] = bt
        ev.append((bt, "pop2", 1.0))
        ev.append((bt + 0.05, "coin", 0.7))
    ev.append((0.9, "pop2", 0.35))  # sticky note
    sc["_R"] = R
    return ev


# ------------------------------------------------------------------ draw: rows
def _row_geom(ctx, top, n, gap, maxh):
    avail = ctx.h * 0.96 - top
    rh = min(maxh, (avail - gap * (n - 1)) / max(1, n))
    return rh


def draw_list(ctx, sc, t, tl, mode):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    items = v["items"]
    n = len(items)
    gap = 9 * k
    rh = _row_geom(ctx, top, n, gap, 78 * k)
    x0, x1 = ctx.w * 0.06, ctx.w * 0.94
    cols = [th.accent, th.accent2, th.accent3]
    if mode == "steps":
        lx = x0 + rh * 0.5
        gl = min(1.0, max(0.0, (t - R["it"][0]) / max(0.3, R["it"][-1] - R["it"][0] + 0.6))) if n > 1 else 0
        ctx.line([(lx, top + rh * 0.5), (lx, top + rh * 0.5 + (n - 1) * (rh + gap) * gl)], mix(th.accent, (255, 255, 255), 0.55), 4 * k)
    for i, it in enumerate(items):
        p = pop(t, R["it"][i], 0.38)
        if p <= 0:
            continue
        pc = min(p, 1.0)
        y0 = top + i * (rh + gap)
        yc = y0 + rh / 2
        col = cols[i % 3]
        if mode == "bullets":
            hh = rh / 2 * pc
            ctx.rr(x0, yc - hh, x1, yc + hh, 16 * k, fill=mix(col, (255, 255, 255), 0.86))
            icn = it.get("icon") if it.get("icon") in ICONS else None
            badge(ctx, x0 + rh * 0.5, yc, rh * 0.36 * pc, icn or str(i + 1), th, th.white, col)
            tx = x0 + rh * 1.0
        elif mode == "steps":
            badge(ctx, x0 + rh * 0.5, yc, rh * 0.38 * pc, str(i + 1), th, th.white, col)
            tx = x0 + rh * 1.05
        else:  # checklist
            r = rh * 0.34 * pc
            ctx.circle(x0 + rh * 0.45, yc, r, fill=th.accent3)
            if pc > 0.7:
                icon(ctx, "check", x0 + rh * 0.45, yc, rh * 0.5, th.white)
            tx = x0 + rh * 0.95
        if pc > 0.55:
            lines, sz = fit(ctx, it["text"], 25 * k, "Bold", x1 - tx - 12 * k, 2)
            lh = sz * 1.18
            for j, ln in enumerate(lines):
                ctx.text(tx, yc + (j - (len(lines) - 1) / 2) * lh, ln, sz, th.ink, "Bold", "lm")


def draw_title(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    p = pop(t, 0.2, 0.5)
    ic = v.get("icon") if v.get("icon") in ICONS else "sparkle"
    icon(ctx, ic, ctx.w / 2, ctx.h * 0.2, 40 * k * min(p, 1.2), th.accent, th.soft)
    h = str(v.get("heading", ""))
    lines, sz = fit(ctx, h, 60 * k, "Bold", ctx.w * 0.88, 3)
    lh = sz * 1.2
    y_top = ctx.h * 0.36
    n = int(max(0, t - R["h0"]) * R["cps"])
    typed_lines(ctx, lines, n, ctx.w / 2, y_top, sz, "Bold", th.ink, lh)
    if int(t * 2.6) % 2 == 0 and n < sum(len(l) + 1 for l in lines):
        li = _line_of(lines, n)
        last = lines[li]
        shown = last[: max(0, n - sum(len(l) + 1 for l in lines[:li]))]
        x = ctx.w / 2 - ctx.tw(last, sz, "Bold") / 2 + ctx.tw(shown, sz, "Bold") + 5 * k
        yy = y_top + li * lh + lh / 2
        ctx.rr(x, yy - sz * 0.5, x + 4 * k, yy + sz * 0.5, 2, fill=th.accent)
    sub = str(v.get("sub", ""))
    g = ease_out((t - R["sub"]) / 0.4)
    if sub and g > 0:
        sl, ss = fit(ctx, sub, 26 * k, "Medium", ctx.w * 0.84, 2)
        y = y_top + lh * len(lines) + 14 * k
        for j, ln in enumerate(sl):
            ctx.text(ctx.w / 2, y + j * ss * 1.25 + (1 - g) * 10 * k, ln, ss, mix(th.card, th.muted, g), "Medium")


def draw_big_number(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    p = pop(t, 0.2, 0.45)
    ic = v.get("icon") if v.get("icon") in ICONS else "coin"
    icon(ctx, ic, ctx.w / 2, ctx.h * 0.16, 30 * k * min(p, 1.2), th.accent, th.soft)
    lab = str(v.get("label", ""))
    if lab:
        for j, ln in enumerate(fit(ctx, lab, 28 * k, "Medium", ctx.w * 0.86, 2)[0]):
            ctx.text(ctx.w / 2, ctx.h * 0.31 + j * 32 * k, ln, 28 * k, th.muted, "Medium")
    try:
        val = float(str(v.get("value", 0)).replace(",", ""))
        numeric = True
    except ValueError:
        numeric = False
    if numeric:
        cur = val * prog(t, R["n0"], R["n1"] - R["n0"])
        s = f'{v.get("prefix", "")}{inr(cur)}{v.get("suffix", "")}'
    else:
        s = str(v.get("value", ""))
    size = 96 * k
    while ctx.tw(s, size, "Bold") > ctx.w * 0.9 and size > 30:
        size *= 0.93
    ctx.text(ctx.w / 2, ctx.h * 0.55, s, size, th.accent, "Bold")
    sub = str(v.get("sub", ""))
    g = ease_out((t - R["n1"] - 0.1) / 0.4)
    if sub and g > 0:
        for j, ln in enumerate(fit(ctx, sub, 28 * k, "Bold", ctx.w * 0.86, 2)[0]):
            ctx.text(ctx.w / 2, ctx.h * 0.74 + j * 34 * k + (1 - g) * 8 * k, ln, 28 * k, mix(th.card, th.ink, g), "Bold")


def draw_split_bar(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    segs = v["segments"]
    tot = sum(max(1.0, float(s["pct"])) for s in segs)
    x0, x1 = ctx.w * 0.06, ctx.w * 0.94
    by0 = top + 14 * k
    bh = 74 * k
    ctx.rr(x0, by0, x1, by0 + bh, 24 * k, fill=mix(th.card, th.ink, 0.06))
    gap = 6 * k
    avail = (x1 - x0) - gap * (len(segs) + 1)
    x = x0 + gap
    for i, s in enumerate(segs):
        share = max(1.0, float(s["pct"])) / tot
        wseg = avail * share
        g = prog(t, R["it"][i], 0.55)
        col = th.segs[i % 4]
        if g > 0:
            ctx.rr(x, by0 + 8 * k, x + max(10 * k, wseg * g), by0 + bh - 8 * k, 18 * k, fill=col)
            if g > 0.7:
                ctx.text(x + wseg / 2, by0 + bh / 2, f'{int(float(s["pct"]))}%', min(34 * k, wseg * 0.3), th.white, "Bold")
            lp = pop(t, R["it"][i] + 0.3, 0.4)
            if lp > 0:
                cx = x + wseg / 2
                lab = str(s["label"])
                lsz = min(27 * k, max(15 * k, wseg / max(4, len(lab)) * 1.6))
                ctx.circle(cx, by0 + bh + 34 * k, 6 * k * min(lp, 1), fill=col)
                ctx.text(cx, by0 + bh + 62 * k, lab, lsz * min(lp, 1) + 1, col, "Bold")
                note = str(s.get("note", ""))
                if note:
                    nl = fit(ctx, note, 21 * k, "Medium", max(wseg + gap, 90 * k), 2)[0]
                    for j, ln in enumerate(nl):
                        ctx.text(cx, by0 + bh + 92 * k + j * 25 * k, ln, 21 * k, th.ink, "Medium")
        x += wseg + gap


def draw_compare(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    gap = 14 * k
    pw = (ctx.w * 0.88 - gap) / 2
    px = [ctx.w * 0.06, ctx.w * 0.06 + pw + gap]
    sides = [("left", th.accent3 if False else (214, 96, 110), "x"), ("right", th.accent3, "ok")]
    for si, (key, col, kind) in enumerate(sides):
        blk = v[key]
        ctx.rr(px[si], top, px[si] + pw, ctx.h * 0.96, 20 * k, fill=mix(col, (255, 255, 255), 0.88))
        ctx.rr(px[si], top, px[si] + pw, top + 44 * k, 20 * k, fill=col)
        ctx.text(px[si] + pw / 2, top + 22 * k, str(blk.get("title", "")), 24 * k, th.white, "Bold")
        items = blk["items"][:4]
        n = max(1, len(items))
        rh = min(70 * k, (ctx.h * 0.96 - top - 54 * k) / n)
        times = R["l"] if key == "left" else R["r"]
        for i, it in enumerate(items):
            p = pop(t, times[i] if i < len(times) else 1.0, 0.36)
            if p <= 0:
                continue
            yc = top + 54 * k + i * rh + rh / 2
            r = min(14 * k, rh * 0.28) * min(p, 1)
            cxm = px[si] + 24 * k
            ctx.circle(cxm, yc, r, fill=col)
            if kind == "ok":
                icon(ctx, "check", cxm, yc, r * 1.9, th.white)
            else:
                ctx.line([(cxm - r * 0.4, yc - r * 0.4), (cxm + r * 0.4, yc + r * 0.4)], th.white, 2.6 * k)
                ctx.line([(cxm - r * 0.4, yc + r * 0.4), (cxm + r * 0.4, yc - r * 0.4)], th.white, 2.6 * k)
            if p > 0.55:
                lines, sz = fit(ctx, it, 25 * k, "Bold", pw - 56 * k, 3)
                for j, ln in enumerate(lines):
                    ctx.text(px[si] + 44 * k, yc + (j - (len(lines) - 1) / 2) * sz * 1.15, ln, sz, th.ink, "Bold", "lm")


def draw_bars(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    items = v["items"]
    n = len(items)
    mx = max(float(i["value"]) for i in items) or 1.0
    gap = 12 * k
    rh = min(66 * k, (ctx.h * 0.95 - top - gap * (n - 1)) / n)
    lab_w = ctx.w * 0.30
    x0, x1 = ctx.w * 0.06 + lab_w, ctx.w * 0.80
    for i, it in enumerate(items):
        g = prog(t, R["it"][i], 0.7)
        y0 = top + i * (rh + gap)
        yc = y0 + rh / 2
        col = th.segs[i % 4]
        lines, sz = fit(ctx, it["label"], 22 * k, "Bold", lab_w - 10 * k, 2)
        if g > 0.02:
            for j, ln in enumerate(lines):
                ctx.text(ctx.w * 0.06, yc + (j - (len(lines) - 1) / 2) * sz * 1.15, ln, sz, th.ink, "Bold", "lm")
        ctx.rr(x0, yc - rh * 0.3, x1, yc + rh * 0.3, rh * 0.3, fill=mix(th.card, th.ink, 0.06))
        wv = (x1 - x0) * float(it["value"]) / mx * g
        if wv > 1:
            ctx.rr(x0, yc - rh * 0.3, x0 + max(rh * 0.6, wv), yc + rh * 0.3, rh * 0.3, fill=col)
        if g > 0.5:
            ctx.text(x1 + 12 * k, yc, f'{it.get("prefix", "")}{inr(float(it["value"]) * g)}{it.get("suffix", "")}', 24 * k, col, "Bold", "lm")


def draw_quote(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    p = pop(t, R["q0"], 0.5)
    ctx.text(ctx.w / 2, ctx.h * 0.2 + (1 - min(p, 1)) * 14 * k, "“", 140 * k * min(p, 1.1) + 1, th.accent, "lora")
    lines, sz = fit(ctx, v["text"], 38 * k, "lora", ctx.w * 0.8, 5)
    lh = sz * 1.3
    y0 = ctx.h * 0.58 - lh * len(lines) / 2
    for i, ln in enumerate(lines):
        g = ease_out((t - R["q0"] - 0.35 - i * 0.18) / 0.35)
        if g > 0:
            ctx.text(ctx.w / 2, y0 + i * lh + lh / 2 + (1 - g) * 10 * k, ln, sz, mix(th.card, th.ink, g), "lora")
    by = str(v.get("by", ""))
    g = ease_out((t - R["q0"] - 0.35 - len(lines) * 0.18) / 0.4)
    if by and g > 0:
        ctx.text(ctx.w / 2, ctx.h * 0.9, "— " + by, 22 * k, mix(th.card, th.muted, g), "Medium")


def draw_cta(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    pr = v["_product"]
    p = pop(t, R["card"], 0.5)
    land = ctx.w / ctx.h > 1.3
    cw, ch = (ctx.w * 0.34, ctx.h * 0.86) if land else (ctx.w * 0.36, ctx.h * 0.72)
    cx0, cy0 = ctx.w * 0.05, ctx.h * 0.07 if land else ctx.h * 0.08
    s = min(p, 1.05)
    ctx.rr(cx0 + cw * (1 - s) / 2, cy0 + ch * (1 - s) / 2, cx0 + cw * (1 + s) / 2, cy0 + ch * (1 + s) / 2, 20 * k,
           fill=th.soft, outline=th.accent, width=3 * k)
    if p > 0.8:
        ccx = cx0 + cw / 2
        ctx.text(ccx, cy0 + 24 * k, v.get("badge", "PDF · instant download"), 14 * k, th.muted, "Medium")
        lines, sz = fit(ctx, pr["title"], 28 * k, "Bold", cw - 26 * k, 5)
        ty = cy0 + ch * 0.18
        for j, ln in enumerate(lines):
            ctx.text(ccx, ty + j * sz * 1.18, ln, sz, th.accent if j % 2 else th.ink, "Bold")
        ctx.rr(ccx - cw * 0.3, cy0 + ch * 0.78, ccx + cw * 0.3, cy0 + ch * 0.78 + 34 * k, 17 * k, fill=th.white)
        ctx.text(ccx, cy0 + ch * 0.78 + 17 * k, pr["price"], 20 * k, th.ink, "Bold")
        ctx.text(ccx, cy0 + ch - 20 * k, "Uzma Azreen", 15 * k, th.muted, "Medium")
    items = v["items"]
    ix = cx0 + cw + ctx.w * 0.05
    top = ctx.h * 0.12
    for i, it in enumerate(items):
        pp = pop(t, R["it"][i], 0.36)
        if pp <= 0:
            continue
        yc = top + i * 56 * k
        ctx.circle(ix + 14 * k, yc, 14 * k * min(pp, 1), fill=th.accent3)
        if pp > 0.7:
            icon(ctx, "check", ix + 14 * k, yc, 26 * k, th.white)
            lines, sz = fit(ctx, it["text"], 23 * k, "Bold", ctx.w - ix - 50 * k, 2)
            for j, ln in enumerate(lines):
                ctx.text(ix + 38 * k, yc + (j - (len(lines) - 1) / 2) * sz * 1.15, ln, sz, th.ink, "Bold", "lm")
    bp = pop(t, R["btn"], 0.45)
    if bp > 0:
        pulse = 1 + 0.03 * math.sin((t - R["btn"]) * 6)
        w, h = min(ctx.w - ix - 10 * k, 300 * k) * min(bp, 1.1) * pulse, 60 * k * min(bp, 1.1) * pulse
        cxm, cym = ix + min(ctx.w - ix - 10 * k, 300 * k) / 2, ctx.h * 0.82 if not land else ctx.h * 0.78
        ctx.rr(cxm - w / 2, cym - h / 2, cxm + w / 2, cym + h / 2, 30 * k, fill=th.accent)
        if bp > 0.8:
            ctx.text(cxm, cym, v.get("btn_text", "Link in bio"), 23 * k, th.white, "Bold")


def draw_cover(ctx, sc, t, tl):
    """Product cover (real image) on the left, title / subtitle / price on the right."""
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    img = v.get("_img")
    W, H = ctx.w, ctx.h
    cx, cy = W * 0.29, H * 0.5
    p = pop(t, R["c0"], 0.55)
    if p > 0:
        h = H * 0.78 * min(p, 1.06)
        if img is not None:
            w = h * img.width / img.height
            if w > W * 0.5:
                w, h = W * 0.5, W * 0.5 * img.height / img.width
            thumb = img.convert("RGBA").resize((max(2, int(w * S2)), max(2, int(h * S2))), Image.LANCZOS)
            pad = int(6 * S2)
            frame = Image.new("RGBA", (thumb.width + pad * 2, thumb.height + pad * 2), (255, 255, 255, 255))
            frame.alpha_composite(thumb, (pad, pad))
            ang = -4 + math.sin(t * 1.4) * 0.8
            rot = frame.rotate(ang, expand=True, resample=Image.BICUBIC)
            shadow = Image.new("RGBA", rot.size, (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 70), (0, 0), rot.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(10 * S2))
            ox, oy = int(cx * S2 - rot.width / 2), int(cy * S2 - rot.height / 2)
            ctx.img.alpha_composite(shadow, (ox + int(6 * S2), oy + int(12 * S2)))
            ctx.img.alpha_composite(rot, (ox, oy))
        else:
            ctx.circle(cx, cy, h * 0.42, fill=th.soft)
            doodles.draw(ctx, "book", cx, cy, h * 0.3, prog(t, R["c0"], 1.0), th.ink)
    tx = W * 0.56
    tw = W * 0.40
    g = ease_out((t - R["t0"]) / 0.45)
    if g > 0:
        lines, sz = fit(ctx, str(v.get("title", "")), 31 * k, "Bold", tw, 4)
        y = H * 0.30
        for j, ln in enumerate(lines):
            ctx.text(tx, y + j * sz * 1.18 + (1 - g) * 10 * k, ln, sz, mix(th.card, th.accent if j % 2 else th.ink, g), "Bold", "lm")
        sub = str(v.get("sub", ""))
        if sub:
            sl, ssz = fit(ctx, sub, 19 * k, "Medium", tw, 4)
            sy = y + len(lines) * sz * 1.18 + 10 * k
            for j, ln in enumerate(sl):
                ctx.text(tx, sy + j * ssz * 1.25, ln, ssz, mix(th.card, th.muted, g), "Medium", "lm")
    pp = pop(t, R["pr"], 0.45)
    if pp > 0 and v.get("price"):
        bw, bh = 150 * k * min(pp, 1.08), 54 * k * min(pp, 1.08)
        bx, by = tx + 10 * k, H * 0.84
        ctx.rr(bx, by - bh / 2, bx + bw, by + bh / 2, bh / 2, fill=th.accent)
        if pp > 0.8:
            ctx.text(bx + bw / 2, by, str(v["price"]), 28 * k, th.white, "Bold")


def _arrow(ctx, x0, y0, x1, y1, p, col, lw):
    if p <= 0:
        return
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2 - abs(x1 - x0) * 0.12 - abs(y1 - y0) * 0.0
    pts = []
    n = 14
    for i in range(int(n * min(1, p)) + 1):
        u = i / n
        pts.append(((1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u * u * y1))
    if len(pts) > 1:
        ctx.line(pts, col, lw)
    if p >= 1:
        a = math.atan2(y1 - my, x1 - mx)
        h = lw * 3.2
        for da in (2.6, -2.6):
            ctx.line([(x1, y1), (x1 + h * math.cos(a + da), y1 + h * math.sin(a + da))], col, lw)


def draw_doodle_flow(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    items = v["items"]
    n = len(items)
    land = ctx.w / ctx.h > 1.3
    cols = n if n <= 3 or land else 2
    rows = (n + cols - 1) // cols
    cw = ctx.w * 0.92 / cols
    area_h = ctx.h * 0.97 - top
    ch = area_h / rows
    size = min(cw * 0.34, ch * 0.34, 96 * k)
    centers = []
    for i in range(n):
        r, c = divmod(i, cols)
        cx = ctx.w * 0.04 + cw * (c + 0.5)
        cy = top + ch * (r + 0.5) - size * 0.3
        centers.append((cx, cy))
    cols_ = [th.accent, th.accent2, th.accent3]
    for i, it in enumerate(items):
        cx, cy = centers[i]
        ts = R["it"][i]
        if i > 0 and (centers[i - 1][1] == cy):
            px, py = centers[i - 1]
            _arrow(ctx, px + size * 1.1, py, cx - size * 1.1, cy, prog(t, ts - 0.35, 0.4), th.muted, max(2, size * 0.06))
        if t < ts:
            continue
        bob = math.sin((t - ts) * 2.4 + i) * size * 0.03
        p = prog(t, ts, 0.9)
        ctx.circle(cx, cy + bob, size * 1.12 * min(1, pop(t, ts, 0.35)), fill=mix(th.card, cols_[i % 3], 0.14))
        doodles.draw(ctx, it.get("icon") or "sparkle", cx, cy + bob, size * 0.82, p, th.ink)
        lp = pop(t, ts + 0.7, 0.35)
        if lp > 0:
            lines, sz = fit(ctx, it["text"], 25 * k, "Bold", cw * 0.92, 2)
            for j, ln in enumerate(lines):
                ctx.text(cx, cy + size * 1.5 + j * sz * 1.2 + (1 - min(lp, 1)) * 6 * k, ln, sz, th.ink, "Bold")


def draw_doodle_big(ctx, sc, t, tl):
    v, R, th, k = sc["v"], sc["_R"], ctx.th, ctx.k
    top = head(ctx, v, t, R)
    land = ctx.w / ctx.h > 1.3
    avail = ctx.h - top
    cy = top + avail * (0.44 if not v.get("sub") else 0.36)
    size = min(ctx.w * 0.2, avail * (0.30 if not v.get("sub") else 0.245))
    cx = ctx.w / 2
    bob = math.sin(t * 2.0) * size * 0.03
    ctx.circle(cx, cy + bob, size * 1.25 * min(1, pop(t, R["d0"] - 0.1, 0.4)), fill=th.soft)
    doodles.draw(ctx, v.get("doodle") or "sparkle", cx, cy + bob, size, prog(t, R["d0"], 1.2), th.ink)
    ex = v.get("extras", [])
    for j, nm in enumerate(ex[:3]):
        te = 1.9 + 0.35 * j
        ang = (-150 + 150 * j / max(1, len(ex) - 1) if len(ex) > 1 else -90) if False else None
        sx = cx + (-1) ** j * size * (1.7 + 0.35 * (j // 2)) if land else cx + (-1) ** j * size * (1.55 + 0.25 * (j // 2))
        sy = cy + (-0.55 if j == 0 else 0.5 if j == 1 else -0.9) * size + math.sin(t * 1.8 + j * 2) * size * 0.05
        pp = pop(t, te, 0.4)
        if pp > 0:
            ctx.circle(sx, sy, size * 0.5 * min(pp, 1.1), fill=mix(th.card, [th.accent, th.accent2, th.accent3][j % 3], 0.14))
            doodles.draw(ctx, nm, sx, sy, size * 0.36 * min(pp, 1.1), prog(t, te, 0.6), th.ink)
    sub = str(v.get("sub", ""))
    g = ease_out((t - R["cap"]) / 0.4)
    if sub and g > 0:
        lines, sz = fit(ctx, sub, 30 * k, "Bold", ctx.w * 0.86, 2)
        y = min(cy + size * 1.5, ctx.h * 0.95 - len(lines) * sz * 1.22)
        for j, ln in enumerate(lines):
            ctx.text(cx, y + j * sz * 1.22 + (1 - g) * 8 * k, ln, sz, mix(th.card, th.ink, g), "Bold")


def draw(ctx, sc, t, tl):
    ty = sc["v"]["type"]
    if ty in ("bullets", "steps", "checklist"):
        draw_list(ctx, sc, t, tl, ty)
    else:
        globals()["draw_" + ty](ctx, sc, t, tl)
