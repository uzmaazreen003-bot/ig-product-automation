"""Half-body animated character from the owner's own anime illustration (cutout, blink, lip-sync)."""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

from common import ROOT

SRC = os.path.join(ROOT, "assets", "character.png")
CROP = (290, 50, 770, 830)
OX, OY = CROP[0], CROP[1]
SS = 3

LIP = (216, 128, 118)
INSIDE = (104, 40, 46)
TONGUE = (226, 122, 130)
TEETH = (250, 240, 234)
LASH = (62, 36, 30)

MOUTH_C = (517.0, 243.5)
EYES = [
    dict(poly=[(461, 197), (468, 191), (480, 189), (491, 193), (494, 202), (488, 207), (474, 207), (464, 203)],
         lash=[(460, 197), (477, 205), (494, 198)], sample=(475, 216)),
    dict(poly=[(528, 186), (536, 179), (548, 177), (558, 180), (562, 188), (556, 196), (542, 197), (532, 192)],
         lash=[(527, 186), (545, 195), (562, 187)], sample=(545, 207)),
]


def cutout():
    im = Image.open(SRC).convert("RGB")
    a = np.asarray(im).astype(int)
    white = (a[..., 0] >= 236) & (a[..., 1] >= 236) & (a[..., 2] >= 236)
    lab, _ = ndimage.label(white)
    border = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])))
    border.discard(0)
    bg = np.isin(lab, list(border))
    fg = ndimage.binary_erosion(~bg, iterations=2)
    alpha = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    rgba = im.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba.crop(CROP)


def _p(pt):
    return ((pt[0] - OX) * SS, (pt[1] - OY) * SS)


def _skin(img, pt):
    x, y = int((pt[0] - OX) * SS), int((pt[1] - OY) * SS)
    patch = np.asarray(img.convert("RGB").crop((x - 6, y - 4, x + 6, y + 4))).reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))


def mouth_variant(big, kind):
    if kind == "closed":
        return big.copy()
    out = big.copy()
    sa, sb = _skin(big, (486, 247)), _skin(big, (551, 245))
    skin = tuple((x + y) // 2 for x, y in zip(sa, sb))
    mask = Image.new("L", big.size, 0)
    cx, cy = _p(MOUTH_C)
    ImageDraw.Draw(mask).ellipse((cx - 25 * SS, cy - 10.5 * SS, cx + 25 * SS, cy + 12 * SS), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.6 * SS))
    cover = Image.new("RGBA", big.size, skin + (255,))
    cover.putalpha(mask)
    out.alpha_composite(cover)
    d = ImageDraw.Draw(out)
    cy = cy + 1 * SS
    if kind == "small":
        w, h = 7 * SS, 3.4 * SS
        d.ellipse((cx - w, cy - h, cx + w, cy + h), fill=INSIDE, outline=LIP, width=int(1.5 * SS))
    elif kind == "wide":
        w, h = 9.5 * SS, 7 * SS
        d.ellipse((cx - w, cy - h * 0.8, cx + w, cy + h * 1.0), fill=INSIDE, outline=LIP, width=int(1.6 * SS))
        d.ellipse((cx - 5 * SS, cy + 1.5 * SS, cx + 5 * SS, cy + 6 * SS), fill=TONGUE)
    elif kind == "o":
        w, h = 5 * SS, 6 * SS
        d.ellipse((cx - w, cy - h, cx + w, cy + h), fill=INSIDE, outline=LIP, width=int(1.6 * SS))
    elif kind == "e":
        w, h = 10 * SS, 3.6 * SS
        d.rounded_rectangle((cx - w, cy - h, cx + w, cy + h), radius=int(3.4 * SS), fill=INSIDE, outline=LIP,
                            width=int(1.5 * SS))
        d.rectangle((cx - w + 3 * SS, cy - h + 1.5 * SS, cx + w - 3 * SS, cy - 0.2 * SS), fill=TEETH)
    return out


def blink_variant(big):
    out = big.copy()
    for e in EYES:
        skin = _skin(big, e["sample"])
        layer = Image.new("RGBA", big.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon([_p(pt) for pt in e["poly"]], fill=skin + (255,))
        layer = layer.filter(ImageFilter.GaussianBlur(1.1 * SS))
        out.alpha_composite(layer)
        d = ImageDraw.Draw(out)
        (xl, yl), (xm, ym), (xr, yr) = [_p(pt) for pt in e["lash"]]
        pts = []
        for i in range(25):
            t = i / 24
            pts.append(((1 - t) ** 2 * xl + 2 * (1 - t) * t * xm + t ** 2 * xr,
                        (1 - t) ** 2 * yl + 2 * (1 - t) * t * ym + t ** 2 * yr))
        d.line(pts, fill=LASH + (255,), width=int(2.2 * SS), joint="curve")
    return out


def build(width=320, kinds=("closed", "small", "wide", "o", "e")):
    base = cutout()
    big = base.resize((base.width * SS, base.height * SS), Image.LANCZOS)
    scale = width / base.width
    size = (width, int(round(base.height * scale)))
    variants = {}
    for kind in kinds:
        mv = mouth_variant(big, kind)
        for blink in (False, True):
            img = blink_variant(mv) if blink else mv
            variants[(kind, blink)] = img.resize(size, Image.LANCZOS)
    return variants, size
