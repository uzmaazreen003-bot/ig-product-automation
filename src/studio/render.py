"""Frame renderer + video assembly (long 16:9 and Shorts 9:16)."""
import bisect
import math
import multiprocessing as mp
import subprocess

from PIL import Image, ImageDraw, ImageFilter

import char
import scenes
from common import Ctx, F, S2, Theme, build_bg, clamp, ease_back, mix, star_pts

FPS = 24
PILL_TEXT = {"money": "MONEY TIP", "overthinking": "MIND TIP", "selfcare": "SELF-CARE", "mental_load": "HOME TIP", "product": "DIGITAL GUIDE"}
VISEMES = ["wide", "small", "o", "e", "wide", "small", "e", "o"]


class Renderer:
    def __init__(self, plan, cfg):
        self.plan = plan
        self.land = plan["format"] == "long"
        self.W, self.H = (1280, 720) if self.land else (720, 1280)
        self.th = Theme(plan["palette"])
        self.sc = plan["scenes"]
        self.starts = [s["t0"] for s in self.sc]
        self.total = plan["total"]
        self.handle = cfg.get("handle", "@uzmaazreen.studio")
        self.link_text = plan.get("link_text", "Link in bio")
        self.pill_text = plan.get("pill_text", "Roz naye tips • Subscribe")
        if self.land:
            self.card = (40, 92, 800, 430)
            self.cap = dict(cx=440, cy=585, size=42, maxw=780)
            self.char_w, self.char_x = 290, 1280 - 290 - 26
            self.note = dict(x=884, y=96, w=352, h=140, ang=-3)
            self.pill = (40, 650, 330, 46)
            self.sparks = [(870, 560, 11, 0.0, "a"), (1000, 40, 8, 1.7, "b"), (700, 676, 9, 3.1, "a"), (900, 20, 7, 2.2, "a")]
        else:
            self.card = (40, 140, 640, 450)
            self.cap = dict(cx=360, cy=652, size=50, maxw=660)
            self.char_w, self.char_x = 330, 720 - 330 - 8
            self.note = dict(x=40, y=772, w=330, h=190, ang=-4)
            self.pill = (40, 1020, 300, 52)
            self.sparks = [(70, 1130, 12, 0.0, "a"), (210, 1210, 9, 1.3, "b"), (340, 1120, 8, 2.4, "a"),
                           (120, 1255, 7, 3.3, "a"), (620, 720, 10, 1.9, "b")]
        self.bg = build_bg(self.th, self.W, self.H)
        self.static = self._static(plan)
        cw, ch = self.card[2], self.card[3]
        base = Image.new("RGBA", (cw * S2, ch * S2), (0, 0, 0, 0))
        ImageDraw.Draw(base).rounded_rectangle((0, 0, cw * S2 - 1, ch * S2 - 1), radius=40 * S2,
                                                fill=self.th.card + (255,))
        self.card_base = base
        self.variants, (self.cw_, self.ch_) = char.build(self.char_w)
        self._notes = {}

    # ---------------------------------------------------------------- static layer
    def _static(self, plan):
        th, W, H = self.th, self.W, self.H
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cx, cy, cw, ch = self.card
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((cx, cy + 10, cx + cw, cy + ch + 10), radius=40, fill=mix(th.ink, (255, 255, 255), 0.3) + (70,))
        sh = sh.filter(ImageFilter.GaussianBlur(18))
        im.alpha_composite(sh)
        d = ImageDraw.Draw(im)
        label = PILL_TEXT.get(plan.get("pillar", ""), "TIPS")
        f = F("Bold", 20)
        tw = d.textlength(label, font=f)
        top = 28
        d.rounded_rectangle((40, top, 40 + tw + 56, top + 42), radius=21, fill=th.soft)
        d.ellipse((54, top + 15, 66, top + 27), fill=th.accent)
        d.text((78, top + 21), label, font=f, fill=th.ink, anchor="lm")
        d.text((W - 40, top + 21), self.handle, font=F("Medium", 20), fill=th.muted, anchor="rm")
        px, py, pw, ph = self.pill
        d.rounded_rectangle((px, py, px + pw, py + ph), radius=ph // 2, fill=th.accent)
        d.ellipse((px + 14, py + ph // 2 - 7, px + 28, py + ph // 2 + 7), fill=th.white)
        d.text((px + 40, py + ph // 2), self.pill_text, font=F("Bold", 18), fill=th.white, anchor="lm")
        if not self.land:
            d.text((px, py + ph + 26), self.link_text, font=F("Medium", 20), fill=th.muted, anchor="lm")
        return im

    # ---------------------------------------------------------------- sticky note
    def _note_img(self, si):
        if si in self._notes:
            return self._notes[si]
        n, th = self.note, self.th
        w, h = n["w"], n["h"]
        pad = 26
        im = Image.new("RGBA", ((w + pad * 2) * S2, (h + pad * 2) * S2), (0, 0, 0, 0))
        ctx = Ctx(im, th, w + pad * 2, h + pad * 2)
        ctx.rr(pad + 4, pad + 8, pad + w + 4, pad + h + 8, 18, fill=mix(th.ink, (255, 255, 255), 0.55))
        ctx.rr(pad, pad, pad + w, pad + h, 18, fill=th.soft2, outline=mix(th.accent2, (255, 255, 255), 0.4), width=2)
        ctx.rr(pad + w / 2 - 34, pad - 9, pad + w / 2 + 34, pad + 13, 4, fill=mix(th.accent, (255, 255, 255), 0.3))
        ctx.text(pad + 22, pad + 34, "KEY POINT", 17, th.accent, "Bold", "lm")
        ctx.circle(pad + w - 30, pad + 34, 9, fill=th.accent)
        txt = str(self.sc[si].get("takeaway", "")).strip() or " "
        lines, sz = scenes.fit(ctx, txt, 32, "Bold", w - 44, 3)
        lh = sz * 1.2
        y0 = pad + 66 + (h - 66 - lh * len(lines)) / 2 - 6
        for j, ln in enumerate(lines):
            ctx.text(pad + 22, y0 + j * lh + lh / 2, ln, sz, th.ink, "Bold", "lm")
        im = im.rotate(n["ang"], resample=Image.BICUBIC, expand=True).reduce(S2)
        self._notes[si] = im
        return im

    # ---------------------------------------------------------------- lipsync / captions
    @staticmethod
    def _active(sc, rel):
        cur = None
        for i, (w, a, b) in enumerate(sc["wt"]):
            if a <= rel:
                cur = (i, w, a, b)
            else:
                break
        return cur

    def _mouth(self, sc, ta):
        rel = ta - sc["lead"]
        cur = self._active(sc, rel)
        if cur is None:
            return "closed", 0.0
        i, w, a, b = cur
        if rel > b + 0.03:
            return "closed", 0.0
        dur = max(0.05, b - a)
        syll = max(1, round(len(w) / 2.6))
        k = (rel - a) / dur * syll
        op = math.sin(math.pi * (k - int(k))) ** 0.8
        if op < 0.22:
            return "closed", op
        if op < 0.45:
            return "small", op
        return VISEMES[(sum(ord(c) for c in w) + int(k)) % len(VISEMES)], op

    @staticmethod
    def _blink(t):
        return (t % 3.3) < 0.13 or ((t + 1.7) % 5.3) < 0.12

    def _caption(self, frame, sc, ta):
        rel = ta - sc["lead"]
        cur = self._active(sc, rel)
        if cur is None or rel > sc["wt"][-1][2] + 0.5:
            return
        idx = cur[0]
        words = [w for w, _a, _b in sc["wt"]]
        d = ImageDraw.Draw(frame)
        c = self.cap
        font = F("Bold", c["size"])
        space = d.textlength(" ", font=font) + 4
        for n in (3, 2, 1):
            g0 = (idx // n) * n
            chunk = list(range(g0, min(len(words), g0 + n)))
            widths = [d.textlength(words[i], font=font) for i in chunk]
            total = sum(widths) + space * (len(chunk) - 1)
            if total <= c["maxw"]:
                break
        x = c["cx"] - total / 2
        for i, wd in zip(chunk, widths):
            if i == idx:
                d.rounded_rectangle((x - 14, c["cy"] - c["size"] * 0.72, x + wd + 14, c["cy"] + c["size"] * 0.72),
                                    radius=22, fill=self.th.accent)
                d.text((x, c["cy"]), words[i], font=font, fill=self.th.white, anchor="lm")
            else:
                d.text((x, c["cy"]), words[i], font=font, fill=self.th.ink, anchor="lm")
            x += wd + space

    # ---------------------------------------------------------------- frame
    def frame(self, t):
        th = self.th
        f = self.bg.copy()
        f.paste(self.static, (0, 0), self.static)
        d = ImageDraw.Draw(f)
        d.rectangle((0, 0, self.W, 5), fill=th.soft)
        d.rectangle((0, 0, int(self.W * clamp(t / self.total)), 5), fill=th.accent)
        for (x, y, r, ph, c) in self.sparks:
            tw = 0.5 + 0.5 * math.sin(t * 2.6 + ph)
            col = th.accent if c == "a" else th.accent3
            if tw > 0.12:
                d.polygon(star_pts(x, y, r * tw, 4, 0.25), fill=col)

        si = max(0, bisect.bisect_right(self.starts, t) - 1)
        sc = self.sc[si]
        ta = t - sc["t0"]
        cx, cy, cw, ch = self.card
        card = self.card_base.copy()
        ctx = Ctx(card, th, cw, ch)
        scenes.draw(ctx, sc, ta, sc["len"])
        card = card.reduce(S2)
        e = clamp(ta / 0.4)
        if e < 1:
            s = 0.92 + 0.08 * ease_back(e)
            card = card.resize((int(cw * s), int(ch * s)), Image.BILINEAR)
            a = clamp(ta / 0.18)
            if a < 1:
                card.putalpha(card.getchannel("A").point(lambda v: int(v * a)))
        bob = math.sin(t * 1.4) * 3
        f.paste(card, (cx + (cw - card.width) // 2, int(cy + bob + (ch - card.height) // 2)), card)

        # sticky note
        np_ = ease_back((ta - 0.9) / 0.4) if ta >= 0.9 else 0.0
        if np_ > 0:
            im = self._note_img(si)
            if abs(np_ - 1) > 0.02:
                im = im.resize((max(1, int(im.width * np_)), max(1, int(im.height * np_))), Image.BILINEAR)
            n = self.note
            f.paste(im, (int(n["x"] + n["w"] / 2 - im.width / 2), int(n["y"] + n["h"] / 2 - im.height / 2 + math.sin(t * 1.7) * 2)), im)

        self._caption(f, sc, ta)

        kind, op = self._mouth(sc, ta)
        img = self.variants[(kind, self._blink(t))]
        y0 = int(self.H - self.ch_ + 6 + math.sin(t * 2.2) * 3 + op * 2)
        f.paste(img, (self.char_x, y0), img)
        return f


# ------------------------------------------------------------------ video assembly
_R = None


def _work(i):
    return _R.frame(i / FPS).tobytes()


def render_video(plan, cfg, wav, out_mp4, workers=None, max_seconds=None):
    global _R
    _R = Renderer(plan, cfg)
    total = plan["total"] if max_seconds is None else min(plan["total"], max_seconds)
    n = int(total * FPS)
    workers = workers or max(1, mp.cpu_count())
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{_R.W}x{_R.H}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    ctx = mp.get_context("fork")
    with ctx.Pool(workers) as pool:
        for k, b in enumerate(pool.imap(_work, range(n), chunksize=6)):
            p.stdin.write(b)
            if k % 600 == 0:
                print(f"  frame {k}/{n}", flush=True)
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed")
    return _R
