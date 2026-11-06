"""Turns a script plan + per-scene audio into an absolute timeline (scene starts, word times, sfx events)."""
import scenes

LEAD = 0.4   # silence before narration starts (visuals appear first)
TAIL = 0.5   # pause after narration
FIRST_LEAD = 0.25


def _estimate(hi_tokens, dur):
    ws = []
    for tk in hi_tokens:
        w = len(tk.strip("।,?!.:;")) + 1.8
        if tk[-1:] in "।,?!.:;":
            w += 3.0
        ws.append(w)
    lo, hi = 0.10, max(0.5, dur - 0.18)
    tot = sum(ws) or 1.0
    cur, out = lo, []
    for w in ws:
        span = (hi - lo) * w / tot
        pause = min(0.18, span * 0.3) if w > 0 else 0
        out.append((cur, cur + span - pause))
        cur += span
    return out


def align_words(sc, events, dur):
    """Returns [(en_word, t0, t1)] relative to start of narration audio."""
    hi, en = sc["hi_tokens"], sc["en_tokens"]
    if events and len(events) == len(hi):
        times = [(a, b) for _t, a, b in events]
    else:
        times = _estimate(hi, dur)
    out = []
    nh, ne = len(hi), len(en)
    for i, w in enumerate(en):
        j = i if ne == nh else min(nh - 1, int(round(i * (nh - 1) / max(1, ne - 1))))
        out.append((w, times[j][0], times[j][1]))
    return out


def build(plan, durations, events_per_scene):
    t = 0.0
    voice_items, events = [], []
    for i, sc in enumerate(plan["scenes"]):
        dur = durations[i]
        lead = FIRST_LEAD if i == 0 else LEAD
        sc["lead"] = lead
        sc["dur"] = dur
        sc["t0"] = t
        sc["len"] = lead + dur + TAIL
        sc["wt"] = align_words(sc, events_per_scene[i], dur)
        voice_items.append((sc["audio"], t + lead))
        ev = scenes.prep(sc, sc["len"])
        events.append((t + 0.02, "whoosh", 0.8))
        events.append((t + 0.12, "pop", 0.6))
        for (te, kind, gain) in ev:
            events.append((t + te, kind, gain))
        t += sc["len"]
    plan["total"] = t + 0.4
    return voice_items, events
