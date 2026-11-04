"""Pop-up / 2D-motion style Reels: elements bounce in one by one, short pop + whoosh sound effects.

Everything on screen is the same text/images as the static design (all from data/products.json).
Sound effects are synthesised with ffmpeg (no music, no downloaded audio, nothing to license).
"""
from __future__ import annotations

import math
import os
import subprocess

from PIL import Image, ImageDraw

from . import render
from .render import REEL, SAFE_X, font, pill, price_text, text_block, tick, cover_fit, paste_with_shadow

FPS = 30
POP = 0.42      # seconds an element takes to pop in
EXIT = 0.20     # seconds before a scene ends that elements start leaving
XFADE = 0.30    # background cross-fade


def ease_out_back(t):
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.9, 2.9
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ------------------------------------------------------------------ layers

class Layer:
    def __init__(self, img, pos, delay, sfx="pop", style="pop"):
        self.img, self.pos, self.delay, self.sfx, self.style = img, pos, delay, sfx, style


def _layer(draw_fn, delay, sfx="pop", style="pop"):
    canvas = Image.new("RGBA", REEL, (0, 0, 0, 0))
    draw_fn(canvas, ImageDraw.Draw(canvas))
    bbox = canvas.getbbox()
    if not bbox:
        return None
    pad = 4
    bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(REEL[0], bbox[2] + pad), min(REEL[1], bbox[3] + pad))
    return Layer(canvas.crop(bbox), (bbox[0], bbox[1]), delay, sfx, style)


def _scene_bg(pal, cover, cfg):
    img, _ = render._scene_base(pal, cover, cfg)
    return img.convert("RGB")


def scene_hook(product, text, pal, cover, cfg):
    bg = _scene_bg(pal, cover, cfg)
    L = [
        _layer(lambda c, d: d.rounded_rectangle((REEL[0] // 2 - 70, 640, REEL[0] // 2 + 70, 652), radius=6, fill=pal["accent"]), 0.05, "tick"),
        _layer(lambda c, d: text_block(d, text, "Bold", (SAFE_X, 720, REEL[0] - SAFE_X, 1380), 84, pal["ink"], valign="middle", min_size=44), 0.20, "pop"),
    ]
    return bg, [l for l in L if l]


def scene_cover(product, pal, cover, cfg):
    bg = _scene_bg(pal, cover, cfg)
    art = cover_fit(cover, (860, 880)) if cover is not None else render.typographic_cover(product["title"], pal, (700, 880))
    x = (REEL[0] - art.size[0]) // 2
    y_after = 400 + art.size[1] + 70

    def draw_art(c, d):
        paste_with_shadow(c, art, (x, 400), radius=34)

    def draw_title(c, d):
        text_block(d, product["title"], "Bold", (SAFE_X, y_after, REEL[0] - SAFE_X, y_after + 230), 60, pal["ink"], min_size=36)

    probe = Image.new("RGB", (10, 10))
    ty = text_block(ImageDraw.Draw(probe), product["title"], "Bold", (SAFE_X, y_after, REEL[0] - SAFE_X, y_after + 230), 60, pal["ink"], min_size=36)

    def draw_meta(c, d):
        text_block(d, product.get("meta", ""), "Regular", (SAFE_X, ty + 14, REEL[0] - SAFE_X, ty + 90), 32, pal["accent"], min_size=24)

    L = [_layer(draw_art, 0.05, "pop"), _layer(draw_title, 0.45, "pop"), _layer(draw_meta, 0.75, "tick", "fade")]
    return bg, [l for l in L if l]


def scene_point(product, header, item, idx, total, pal, cover, cfg):
    bg = _scene_bg(pal, cover, cfg)
    card = (SAFE_X - 10, 680, REEL[0] - SAFE_X + 10, 1320)

    def draw_header(c, d):
        text_block(d, header.upper(), "Bold", (SAFE_X, 550, REEL[0] - SAFE_X, 620), 40, pal["accent"], min_size=26)

    def draw_card(c, d):
        d.rounded_rectangle(card, radius=44, fill=pal["card"])

    def draw_tick(c, d):
        tick(d, card[0] + 100, card[1] + 100, 48, pal["accent"], pal["card"])

    def draw_text(c, d):
        text_block(d, item, "Medium", (card[0] + 60, card[1] + 190, card[2] - 60, card[3] - 50), 68, pal["ink"], valign="middle", min_size=38)

    def draw_dots(c, d):
        gap, r = 44, 11
        x0 = REEL[0] // 2 - (total - 1) * gap // 2
        for i in range(total):
            col = pal["accent"] if i == idx else pal["soft"]
            d.ellipse((x0 + i * gap - r, 1410 - r, x0 + i * gap + r, 1410 + r), fill=col)

    L = [_layer(draw_header, 0.05, "tick", "fade"), _layer(draw_card, 0.12, "pop"), _layer(draw_tick, 0.38, "ding"),
         _layer(draw_text, 0.50, "tick", "fade"), _layer(draw_dots, 0.70, None, "fade")]
    return bg, [l for l in L if l]


def scene_cta(product, pal, cover, cfg):
    bg = _scene_bg(pal, cover, cfg)
    y = 430 if cover is not None else 640
    L = []
    if cover is not None:
        art = cover_fit(cover, (440, 520))
        ax, ay = (REEL[0] - art.size[0]) // 2, y
        L.append(_layer(lambda c, d: paste_with_shadow(c, art, (ax, ay), radius=26), 0.05, "pop"))
        y += art.size[1] + 60
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    ty = text_block(probe, product["title"], "Bold", (SAFE_X, y, REEL[0] - SAFE_X, y + 210), 56, pal["ink"], min_size=34)
    L.append(_layer(lambda c, d: text_block(d, product["title"], "Bold", (SAFE_X, y, REEL[0] - SAFE_X, y + 210), 56, pal["ink"], min_size=34), 0.30, "pop"))
    y2 = ty + 30
    ptxt = price_text(product, cfg)
    if ptxt:
        py = y2
        L.append(_layer(lambda c, d: pill(d, REEL[0] // 2, py, ptxt, font(64, "Bold"), pal["accent"], pal["onaccent"]), 0.70, "ding"))
        y2 = pill(probe, REEL[0] // 2, py, ptxt, font(64, "Bold"), pal["accent"], pal["onaccent"]) + 40
    ly = y2
    L.append(_layer(lambda c, d: pill(d, REEL[0] // 2, ly, "Link in bio", font(52, "Bold"), pal["card"], pal["ink"], pad_x=56), 1.10, "pop"))
    y3 = ly + 150

    def draw_small(c, d):
        text_block(d, "Instant digital download", "Regular", (SAFE_X, y3, REEL[0] - SAFE_X, y3 + 60), 34, pal["ink"], min_size=24)
        if product.get("disclaimer"):
            text_block(d, product["disclaimer"], "Regular", (SAFE_X, y3 + 80, REEL[0] - SAFE_X, y3 + 260), 26, pal["ink"], min_size=20)

    L.append(_layer(draw_small, 1.45, None, "fade"))
    return bg, [l for l in L if l]


# ------------------------------------------------------------------ sound effects

def _sfx_expr(kind):
    if kind == "pop":
        return ["-f", "lavfi", "-i", "aevalsrc='0.9*sin(2*PI*(420+900*exp(-t*38))*t)*exp(-t*30)':d=0.16:s=44100"]
    if kind == "tick":
        return ["-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*1500*t)*exp(-t*90)':d=0.08:s=44100"]
    if kind == "ding":
        return ["-f", "lavfi", "-i", "aevalsrc='0.55*(sin(2*PI*1320*t)+0.5*sin(2*PI*1980*t))*exp(-t*9)':d=0.5:s=44100"]
    if kind == "whoosh":
        return ["-f", "lavfi", "-i", "anoisesrc=color=pink:d=0.45:r=44100:a=0.8"]
    raise ValueError(kind)


def build_audio(events, voice, total, out_wav):
    """events: [(time_s, kind)], voice: [(time_s, mp3_path)]. Returns wav path. Never adds music."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100"]
    parts, labels = ["[0:a]atrim=0:%.3f[base]" % total], ["[base]"]
    n = 1
    for t, kind in events:
        cmd += _sfx_expr(kind)
        ms = int(t * 1000)
        extra = ",lowpass=f=2500,highpass=f=300,afade=t=in:d=0.15,afade=t=out:st=0.2:d=0.25" if kind == "whoosh" else ""
        vol = {"pop": 0.55, "tick": 0.35, "ding": 0.45, "whoosh": 0.30}[kind]
        parts.append(f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo{extra},volume={vol},adelay={ms}|{ms}[e{n}]")
        labels.append(f"[e{n}]")
        n += 1
    for t, path in voice:
        cmd += ["-i", path]
        ms = int(t * 1000)
        parts.append(f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms}[e{n}]")
        labels.append(f"[e{n}]")
        n += 1
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95,atrim=0:{total:.3f}[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", out_wav]
    subprocess.run(cmd, check=True)
    return out_wav


# ------------------------------------------------------------------ frame renderer

def _alpha(img, a):
    if a >= 0.999:
        return img.getchannel("A")
    lut = [int(i * a) for i in range(256)]
    return img.getchannel("A").point(lut)


def _draw_layer(frame, layer, t_local, scene_len, last_scene):
    t = t_local - layer.delay
    if t < 0:
        return
    k = ease_out_back(t / POP)
    a = min(1.0, t / (POP * 0.5))
    if layer.style == "fade":
        k, a = 0.94 + 0.06 * min(1, t / POP), min(1.0, t / POP)
    wob = math.sin(t_local * 2.2 + layer.pos[1] * 0.01) * 4 if t > POP else 0   # gentle float
    scale = 0.35 + 0.65 * k if layer.style == "pop" else k
    if not last_scene:
        left = scene_len - t_local
        if left < EXIT:
            x = max(0.0, left / EXIT)
            a *= x
            scale *= 0.92 + 0.08 * x
    if a <= 0.01 or scale <= 0.02:
        return
    w, h = layer.img.size
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    img = layer.img if (nw, nh) == (w, h) else layer.img.resize((nw, nh), Image.BILINEAR)
    cx, cy = layer.pos[0] + w / 2, layer.pos[1] + h / 2 + wob
    frame.paste(img.convert("RGB"), (int(cx - nw / 2), int(cy - nh / 2)), _alpha(img, a))


def _bg_frame(bg, t_local, scene_len, idx):
    zoom = 1.0 + 0.05 * (t_local / scene_len if idx % 2 == 0 else 1 - t_local / scene_len)
    w, h = bg.size
    cw, ch = w / zoom, h / zoom
    box = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
    return bg.resize((w, h), Image.BILINEAR, box=box)


def build_reel(scenes, durations, out_path, audio_wav):
    """scenes: [(bg, [Layer])]; streams frames to ffmpeg and muxes the prepared audio."""
    total = sum(durations)
    n_frames = int(round(total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{REEL[0]}x{REEL[1]}",
           "-r", str(FPS), "-i", "-", "-i", audio_wav, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    starts = [sum(durations[:i]) for i in range(len(durations))]
    try:
        for f in range(n_frames):
            t = f / FPS
            i = max(j for j, s in enumerate(starts) if s <= t + 1e-9)
            tl, sl = t - starts[i], durations[i]
            frame = _bg_frame(scenes[i][0], tl, sl, i)
            if i > 0 and tl < XFADE:   # fade from previous background
                prev = _bg_frame(scenes[i - 1][0], durations[i - 1] + tl, durations[i - 1] + XFADE, i - 1)
                frame = Image.blend(prev, frame, tl / XFADE)
            frame = frame.copy()
            for layer in scenes[i][1]:
                _draw_layer(frame, layer, tl, sl, i == len(durations) - 1)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError("ffmpeg failed while building the Reel")
    return out_path


def events_for(scenes, durations):
    ev, starts = [], [sum(durations[:i]) for i in range(len(durations))]
    for i, (_, layers) in enumerate(scenes):
        if i > 0:
            ev.append((max(0.0, starts[i] - 0.12), "whoosh"))
        for l in layers:
            if l.sfx:
                ev.append((starts[i] + l.delay, l.sfx))
    return ev
