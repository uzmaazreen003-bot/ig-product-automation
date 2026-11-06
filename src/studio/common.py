"""Shared helpers: fonts, easing, drawing context (2x supersampled), themes."""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
S2 = 2

_fc = {}


def F(name, size):
    size = max(4, int(size))
    key = (name, size)
    if key not in _fc:
        if name == "lora":
            f = ImageFont.truetype(os.path.join(FONT_DIR, "Lora-Italic-Variable.ttf"), size)
            try:
                f.set_variation_by_axes([700])
            except Exception:
                pass
        else:
            f = ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{name}.ttf"), size)
        _fc[key] = f
    return _fc[key]


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_back(p):
    p = clamp(p)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def pop(t, t0, dur=0.4):
    return ease_back((t - t0) / dur) if t >= t0 else 0.0


def prog(t, t0, dur):
    return ease_out((t - t0) / dur)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def inr(n):
    n = int(round(n))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + s


# ------------------------------------------------------------------ themes
PALETTES = {
    "blush": dict(bg_top=(254, 247, 242), bg_bot=(249, 222, 229), blob1=(250, 200, 214), blob2=(196, 224, 204),
                  ink=(92, 40, 62), accent=(226, 110, 140), accent2=(244, 172, 124), accent3=(118, 170, 140),
                  muted=(150, 112, 124)),
    "sage": dict(bg_top=(247, 251, 246), bg_bot=(214, 236, 222), blob1=(190, 226, 204), blob2=(250, 226, 190),
                 ink=(34, 70, 56), accent=(76, 150, 114), accent2=(232, 176, 76), accent3=(214, 110, 130),
                 muted=(104, 134, 120)),
    "peach": dict(bg_top=(255, 248, 240), bg_bot=(252, 222, 200), blob1=(255, 206, 170), blob2=(250, 196, 208),
                  ink=(98, 50, 34), accent=(236, 124, 80), accent2=(246, 184, 96), accent3=(116, 164, 144),
                  muted=(156, 118, 98)),
    "lavender": dict(bg_top=(250, 247, 255), bg_bot=(226, 218, 250), blob1=(214, 200, 248), blob2=(252, 206, 224),
                     ink=(60, 42, 98), accent=(136, 104, 208), accent2=(240, 148, 186), accent3=(96, 176, 170),
                     muted=(124, 108, 160)),
    "teal": dict(bg_top=(244, 252, 251), bg_bot=(206, 236, 236), blob1=(176, 226, 226), blob2=(252, 226, 176),
                 ink=(20, 64, 70), accent=(32, 148, 158), accent2=(232, 176, 76), accent3=(224, 112, 124),
                 muted=(90, 132, 138)),
    "sunset": dict(bg_top=(255, 244, 240), bg_bot=(250, 210, 200), blob1=(255, 190, 176), blob2=(252, 226, 170),
                   ink=(84, 32, 52), accent=(212, 80, 110), accent2=(244, 158, 68), accent3=(120, 160, 150),
                   muted=(150, 104, 112)),
}
PALETTE_ORDER = list(PALETTES)


class Theme:
    def __init__(self, name):
        self.name = name
        for k, v in PALETTES[name].items():
            setattr(self, k, v)
        self.card = (255, 252, 249)
        self.white = (255, 255, 255)
        self.soft = mix(self.accent, (255, 255, 255), 0.84)
        self.soft2 = mix(self.accent2, (255, 255, 255), 0.78)
        self.soft3 = mix(self.accent3, (255, 255, 255), 0.82)
        self.segs = [self.accent, self.accent2, self.accent3, self.muted]


def build_bg(th, W, H):
    bg = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(bg)
    for y in range(H):
        px.line([(0, y), (W, y)], fill=mix(th.bg_top, th.bg_bot, y / (H - 1)))
    s = min(W, H)
    for box, col, a in [((-0.3 * s, -0.25 * s, 0.55 * s, 0.55 * s), th.blob1, 120),
                        ((W - 0.5 * s, H - 0.45 * s, W + 0.4 * s, H + 0.4 * s), th.blob2, 110)]:
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).ellipse(box, fill=a)
        m = m.filter(ImageFilter.GaussianBlur(s * 0.1))
        bg.paste(Image.new("RGB", (W, H), col), (0, 0), m)
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for x in range(18, W, 36):
        for y in range(18, H, 36):
            dd.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=th.accent + (34,))
    bg.paste(dots, (0, 0), dots)
    return bg


# ------------------------------------------------------------------ drawing context
class Ctx:
    """Drawing in logical units on a 2x supersampled image. k = scale vs a 640x450 base card."""

    def __init__(self, img, th, w, h):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.th = th
        self.w = w
        self.h = h
        self.k = min(w / 640.0, h / 450.0) * (1.18 if w / h > 1.3 else 1.0)

    def _b(self, box):
        return tuple(v * S2 for v in box)

    def text(self, x, y, s, size, col, font="Bold", anchor="mm"):
        self.d.text((x * S2, y * S2), str(s), font=F(font, size * S2), fill=col, anchor=anchor)

    def tw(self, s, size, font="Bold"):
        return self.d.textlength(str(s), font=F(font, size * S2)) / S2

    def rr(self, x0, y0, x1, y1, r, fill=None, outline=None, width=0):
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        self.d.rounded_rectangle(self._b((x0, y0, x1, y1)), radius=max(1, r * S2), fill=fill, outline=outline,
                                 width=int(width * S2))

    def circle(self, cx, cy, r, fill=None, outline=None, width=0):
        if r < 0.5:
            return
        self.d.ellipse(self._b((cx - r, cy - r, cx + r, cy + r)), fill=fill, outline=outline, width=int(width * S2))

    def line(self, pts, fill, width):
        self.d.line([(x * S2, y * S2) for x, y in pts], fill=fill, width=max(1, int(width * S2)), joint="curve")

    def poly(self, pts, fill):
        self.d.polygon([(x * S2, y * S2) for x, y in pts], fill=fill)

    def arc(self, box, a0, a1, fill, width):
        self.d.arc(self._b(box), a0, a1, fill=fill, width=max(1, int(width * S2)))


def star_pts(cx, cy, r, n=4, inner=0.25, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        ang = math.pi / n * i + rot
        rad = r if i % 2 == 0 else r * inner
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts
