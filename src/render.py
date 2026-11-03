"""Rendering: scene images (Pillow) and Reel video (ffmpeg).

No emojis are drawn into images (the bundled font has none); emojis only appear in captions.
Everything shown on screen comes from data/products.json, which is copied from the product pages.
"""
from __future__ import annotations

import glob
import hashlib
import io
import os
import subprocess
from functools import lru_cache

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")

REEL = (1080, 1920)
POST = (1080, 1350)

PALETTES = [
    dict(bg=(247, 239, 229), card=(255, 252, 247), ink=(59, 42, 32), accent=(201, 113, 75), soft=(232, 214, 196), onaccent=(255, 255, 255)),
    dict(bg=(232, 238, 226), card=(250, 252, 247), ink=(36, 52, 40), accent=(94, 132, 92), soft=(207, 219, 198), onaccent=(255, 255, 255)),
    dict(bg=(246, 229, 229), card=(255, 249, 249), ink=(74, 37, 46), accent=(188, 98, 115), soft=(236, 206, 210), onaccent=(255, 255, 255)),
    dict(bg=(33, 37, 52), card=(48, 53, 72), ink=(244, 238, 228), accent=(240, 184, 106), soft=(66, 72, 96), onaccent=(33, 37, 52)),
    dict(bg=(236, 229, 214), card=(252, 249, 242), ink=(70, 52, 30), accent=(156, 110, 52), soft=(219, 205, 178), onaccent=(255, 255, 255)),
]


def palette_for(product_id: str):
    h = int(hashlib.sha1(product_id.encode()).hexdigest(), 16)
    return PALETTES[h % len(PALETTES)]


# ---------------------------------------------------------------- fonts / text

@lru_cache(maxsize=64)
def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, weight, box_w, box_h, max_size, min_size=28, spacing=1.28):
    """Largest font size whose wrapped text fits the box."""
    size = max_size
    while True:
        fnt = font(size, weight)
        lines = wrap(draw, text, fnt, box_w)
        if len(lines) > 1 and len(lines[-1].split()) == 1 and len(lines[-1]) <= 6:
            balanced = wrap(draw, text, fnt, int(box_w * 0.8))  # avoid a lonely last word
            if len(balanced) == len(lines):
                lines = balanced
        height = int(len(lines) * size * spacing)
        widest = max((draw.textlength(l, font=fnt) for l in lines), default=0)
        if (height <= box_h and widest <= box_w) or size <= min_size:
            return fnt, lines, size, height
        size -= 2


def draw_lines(draw, lines, fnt, size, cx, y, fill, align="center", left=None, spacing=1.28):
    for line in lines:
        if align == "center":
            w = draw.textlength(line, font=fnt)
            draw.text((cx - w / 2, y), line, font=fnt, fill=fill)
        else:
            draw.text((left, y), line, font=fnt, fill=fill)
        y += int(size * spacing)
    return y


def text_block(draw, text, weight, box, max_size, fill, align="center", min_size=26, valign="top"):
    x0, y0, x1, y1 = box
    fnt, lines, size, height = fit_text(draw, text, weight, x1 - x0, y1 - y0, max_size, min_size)
    y = y0 if valign == "top" else y0 + (y1 - y0 - height) // 2
    draw_lines(draw, lines, fnt, size, (x0 + x1) // 2, y, fill, align=align, left=x0)
    return y + height


# ---------------------------------------------------------------- images

def load_cover(product: dict, cache_dir: str):
    """assets/covers/<id>.* wins (manual override), otherwise download product['image']."""
    for p in glob.glob(os.path.join(ROOT, "assets", "covers", f"{product['id']}.*")):
        try:
            return Image.open(p).convert("RGB")
        except Exception:
            pass
    url = product.get("image")
    if not url:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    cached = os.path.join(cache_dir, f"{product['id']}.img")
    try:
        if not os.path.exists(cached):
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (ig-product-automation)"})
            r.raise_for_status()
            with open(cached, "wb") as fh:
                fh.write(r.content)
        return Image.open(cached).convert("RGB")
    except Exception as exc:  # cover is optional: fall back to typographic cards
        print(f"[render] cover not available for {product['id']}: {exc}")
        return None


def cover_fill(img: Image.Image, size):
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.5))


def cover_fit(img: Image.Image, box):
    w, h = img.size
    scale = min(box[0] / w, box[1] / h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def rounded(img: Image.Image, radius: int):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0], img.size[1]), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def paste_with_shadow(canvas: Image.Image, img: Image.Image, xy, radius=36, shadow=(0, 0, 0)):
    x, y = xy
    pad = 60
    sh = Image.new("RGBA", (img.size[0] + pad * 2, img.size[1] + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 14, pad + img.size[0], pad + 14 + img.size[1]), radius=radius, fill=shadow + (70,))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    canvas.alpha_composite(sh, (x - pad, y - pad))
    canvas.alpha_composite(rounded(img, radius), (x, y))


def background(size, pal, cover):
    if cover is not None:
        bg = cover_fill(cover, size).filter(ImageFilter.GaussianBlur(46))
        veil = Image.new("RGB", size, pal["bg"])
        bg = Image.blend(bg, veil, 0.86)
        return bg.convert("RGBA")
    bg = Image.new("RGBA", size, pal["bg"] + (255,))
    d = ImageDraw.Draw(bg, "RGBA")
    d.ellipse((-260, -220, 520, 560), fill=pal["soft"] + (150,))
    d.ellipse((size[0] - 520, size[1] - 700, size[0] + 260, size[1] + 80), fill=pal["soft"] + (150,))
    return bg


def brand_label(draw, size, pal, handle, y):
    fnt = font(34, "Medium")
    label = handle.upper().replace("@", "")
    w = draw.textlength(label, font=fnt)
    draw.text(((size[0] - w) / 2, y), label, font=fnt, fill=pal["accent"])


def pill(draw, cx, y, text, fnt, fill, ink, pad_x=44, pad_y=20):
    w = draw.textlength(text, font=fnt)
    h = fnt.size
    x0, x1 = cx - w / 2 - pad_x, cx + w / 2 + pad_x
    draw.rounded_rectangle((x0, y, x1, y + h + pad_y * 2), radius=(h + pad_y * 2) // 2, fill=fill)
    draw.text((cx - w / 2, y + pad_y - 4), text, font=fnt, fill=ink)
    return y + h + pad_y * 2


def tick(draw, cx, cy, r, color, bg):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    pts = [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.34), (cx + r * 0.46, cy - r * 0.32)]
    draw.line(pts, fill=bg, width=max(4, int(r * 0.2)), joint="curve")


def typographic_cover(title: str, pal, box):
    """Used when the cover image cannot be downloaded."""
    img = Image.new("RGB", box, pal["accent"])
    d = ImageDraw.Draw(img)
    d.rectangle((24, 24, box[0] - 24, box[1] - 24), outline=pal["onaccent"], width=4)
    text_block(d, title, "Bold", (70, 90, box[0] - 70, box[1] - 90), 84, pal["onaccent"], valign="middle")
    return img


def price_text(product, cfg):
    return f"{cfg.get('currency_symbol', '₹')}{product['price']}" if cfg.get("show_price", True) else ""


# ---------------------------------------------------------------- reel scenes (1080x1920)

SAFE_X = 110


def _scene_base(pal, cover, cfg):
    img = background(REEL, pal, cover)
    d = ImageDraw.Draw(img)
    brand_label(d, REEL, pal, cfg["handle"], 270)
    return img, d


def scene_hook(product, text, pal, cover, cfg):
    img, d = _scene_base(pal, cover, cfg)
    d.rounded_rectangle((REEL[0] // 2 - 70, 640, REEL[0] // 2 + 70, 652), radius=6, fill=pal["accent"])
    text_block(d, text, "Bold", (SAFE_X, 720, REEL[0] - SAFE_X, 1380), 84, pal["ink"], valign="middle", min_size=44)
    return img.convert("RGB")


def scene_cover(product, pal, cover, cfg):
    img, d = _scene_base(pal, cover, cfg)
    box = (860, 880)
    art = cover_fit(cover, box) if cover is not None else typographic_cover(product["title"], pal, (700, 880))
    x = (REEL[0] - art.size[0]) // 2
    paste_with_shadow(img, art, (x, 400), radius=34)
    d = ImageDraw.Draw(img)
    y = 400 + art.size[1] + 70
    y = text_block(d, product["title"], "Bold", (SAFE_X, y, REEL[0] - SAFE_X, y + 230), 60, pal["ink"], min_size=36)
    text_block(d, product.get("meta", ""), "Regular", (SAFE_X, y + 14, REEL[0] - SAFE_X, y + 90), 32, pal["accent"], min_size=24)
    return img.convert("RGB")


def scene_point(product, header, item, idx, total, pal, cover, cfg):
    img, d = _scene_base(pal, cover, cfg)
    text_block(d, header.upper(), "Bold", (SAFE_X, 550, REEL[0] - SAFE_X, 620), 40, pal["accent"], min_size=26)
    card = (SAFE_X - 10, 680, REEL[0] - SAFE_X + 10, 1320)
    d.rounded_rectangle(card, radius=44, fill=pal["card"])
    tick(d, card[0] + 100, card[1] + 100, 48, pal["accent"], pal["card"])
    text_block(d, item, "Medium", (card[0] + 60, card[1] + 190, card[2] - 60, card[3] - 50), 68, pal["ink"], valign="middle", min_size=38)
    # progress dots
    gap, r = 44, 11
    x0 = REEL[0] // 2 - (total - 1) * gap // 2
    for i in range(total):
        c = pal["accent"] if i == idx else pal["soft"]
        d.ellipse((x0 + i * gap - r, 1410 - r, x0 + i * gap + r, 1410 + r), fill=c)
    return img.convert("RGB")


def scene_cta(product, pal, cover, cfg):
    img, d = _scene_base(pal, cover, cfg)
    y = 430 if cover is not None else 640
    if cover is not None:
        art = cover_fit(cover, (440, 520))
        paste_with_shadow(img, art, ((REEL[0] - art.size[0]) // 2, y), radius=26)
        y += art.size[1] + 60
        d = ImageDraw.Draw(img)
    y = text_block(d, product["title"], "Bold", (SAFE_X, y, REEL[0] - SAFE_X, y + 210), 56, pal["ink"], min_size=34)
    y += 30
    ptxt = price_text(product, cfg)
    if ptxt:
        y = pill(d, REEL[0] // 2, y, ptxt, font(64, "Bold"), pal["accent"], pal["onaccent"]) + 40
    pill(d, REEL[0] // 2, y, "Link in bio", font(52, "Bold"), pal["card"], pal["ink"], pad_x=56)
    y += 150
    text_block(d, "Instant digital download", "Regular", (SAFE_X, y, REEL[0] - SAFE_X, y + 60), 34, pal["ink"], min_size=24)
    if product.get("disclaimer"):
        text_block(d, product["disclaimer"], "Regular", (SAFE_X, y + 80, REEL[0] - SAFE_X, y + 260), 26, pal["ink"], min_size=20)
    return img.convert("RGB")


# ---------------------------------------------------------------- carousel slides (1080x1350)

def _post_base(pal, cover, cfg):
    img = background(POST, pal, cover)
    d = ImageDraw.Draw(img)
    brand_label(d, POST, pal, cfg["handle"], 60)
    return img, d


def slide_cover(product, hook, pal, cover, cfg):
    img, d = _post_base(pal, cover, cfg)
    art = cover_fit(cover, (780, 640)) if cover is not None else typographic_cover(product["title"], pal, (640, 640))
    paste_with_shadow(img, art, ((POST[0] - art.size[0]) // 2, 140), radius=30)
    d = ImageDraw.Draw(img)
    y = 140 + art.size[1] + 56
    y = text_block(d, product["title"], "Bold", (90, y, POST[0] - 90, y + 170), 56, pal["ink"], min_size=34)
    text_block(d, product.get("subtitle", ""), "Regular", (90, y + 10, POST[0] - 90, y + 110), 30, pal["accent"], min_size=22)
    return img.convert("RGB")


def slide_list(product, header, items, pal, cover, cfg):
    img, d = _post_base(pal, cover, cfg)
    text_block(d, header, "Bold", (80, 140, POST[0] - 80, 260), 56, pal["ink"], min_size=36)
    items = items[:5]
    top, bottom = 290, 1240
    row_h = min(210, (bottom - top) // max(1, len(items)))
    for i, item in enumerate(items):
        y0 = top + i * row_h
        d.rounded_rectangle((70, y0, POST[0] - 70, y0 + row_h - 18), radius=30, fill=pal["card"])
        tick(d, 70 + 62, y0 + (row_h - 18) // 2, 30, pal["accent"], pal["card"])
        text_block(d, item, "Medium", (70 + 120, y0 + 10, POST[0] - 70 - 36, y0 + row_h - 28), 44, pal["ink"], align="left", valign="middle", min_size=22)
    return img.convert("RGB")


def slide_cta(product, pal, cover, cfg):
    img, d = _post_base(pal, cover, cfg)
    y = 190 if cover is not None else 380
    if cover is not None:
        art = cover_fit(cover, (420, 480))
        paste_with_shadow(img, art, ((POST[0] - art.size[0]) // 2, y), radius=24)
        y += art.size[1] + 50
        d = ImageDraw.Draw(img)
    y = text_block(d, product["title"], "Bold", (90, y, POST[0] - 90, y + 170), 52, pal["ink"], min_size=32)
    y += 24
    ptxt = price_text(product, cfg)
    if ptxt:
        y = pill(d, POST[0] // 2, y, ptxt, font(56, "Bold"), pal["accent"], pal["onaccent"]) + 30
    y = pill(d, POST[0] // 2, y, "Link in bio", font(46, "Bold"), pal["card"], pal["ink"], pad_x=50) + 30
    if product.get("disclaimer"):
        text_block(d, product["disclaimer"], "Regular", (90, y, POST[0] - 90, y + 140), 24, pal["ink"], min_size=18)
    return img.convert("RGB")


def save_jpeg(img: Image.Image, path: str):
    img.convert("RGB").save(path, "JPEG", quality=92, optimize=True)
    assert os.path.getsize(path) < 8 * 1024 * 1024, "image over Instagram's 8 MB limit"


def save_png(img: Image.Image, path: str):
    img.convert("RGB").save(path, "PNG")


# ---------------------------------------------------------------- video

FPS = 30
FADE = 0.35


def build_reel(scene_pngs, durations, out_path, ambient=None, workdir=None):
    """Slow zoom on every scene + cross-fades. Audio: silent track, or a quiet natural-sound loop if provided."""
    assert len(scene_pngs) == len(durations) >= 2
    n = len(scene_pngs)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in scene_pngs:
        cmd += ["-i", p]
    total = sum(durations)
    if ambient and os.path.exists(ambient):
        cmd += ["-stream_loop", "-1", "-i", ambient]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    audio_idx = n

    parts = []
    for i, dur in enumerate(durations):
        clip_len = dur + (FADE if i < n - 1 else 0)
        frames = int(round(clip_len * FPS))
        if i % 2 == 0:
            z = f"1+0.06*on/{frames}"
        else:
            z = f"1.06-0.06*on/{frames}"
        parts.append(
            f"[{i}:v]scale=2160:3840,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={REEL[0]}x{REEL[1]}:fps={FPS},setsar=1,format=yuv420p[v{i}]"
        )
    last = "v0"
    offset = 0.0
    for i in range(1, n):
        offset += durations[i - 1]
        out = f"x{i}"
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[{out}]")
        last = out
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", f"{audio_idx}:a"]
    cmd += [
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,duration,r_frame_rate",
         "-show_entries", "format=duration,size", "-of", "default=nw=1", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return out
