"""Optional voice-over through the ElevenLabs API (the user's own account / voice).

Only text that is already in data/products.json (or the fixed CTA line) is ever spoken.
If the key is missing or the API fails, the Reel is still built (silent) and the reason is recorded.
"""
from __future__ import annotations

import os
import subprocess

import requests

API = os.environ.get("ELEVENLABS_BASE", "https://api.elevenlabs.io").rstrip("/")


class VoiceError(Exception):
    pass


def enabled(cfg) -> bool:
    v = cfg.get("voice") or {}
    if not v.get("enabled"):
        return False
    return bool(v.get("voice_id")) if v.get("provider", "edge") == "elevenlabs" else True


def speech_lines(product, script, cfg):
    """One spoken line per scene, in scene order: hook, cover, points..., cta."""
    cur = cfg.get("voice", {}).get("price_word", "rupees")
    lines = [script["hook"]]
    sub = product.get("subtitle")
    lines.append(f"{product['title']}. {sub}" if sub else product["title"])
    lines += list(script["items"])
    cta = (cfg.get("voice", {}).get("cta") or "Link in bio.")
    if cfg.get("show_price", True) and product.get("price"):
        lines.append(f"{product['title']}, sirf {product['price']} {cur}. {cta}")
    else:
        lines.append(f"{product['title']}. {cta}")
    return [l.replace("’", "'").replace("—", ",").strip() for l in lines]


def synth_edge(text, cfg, out_path):
    """Free Microsoft neural voices through the edge-tts package (no key, no account)."""
    import asyncio
    try:
        import edge_tts
    except ImportError:
        raise VoiceError("edge-tts is not installed")
    v = cfg["voice"]

    async def go():
        comm = edge_tts.Communicate(text, v.get("voice", "en-IN-NeerjaNeural"), rate=v.get("rate", "+0%"))
        await asyncio.wait_for(comm.save(out_path), timeout=60)

    last = None
    for _ in range(3):
        try:
            asyncio.run(go())
            if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
                return out_path
            last = "empty audio"
        except Exception as e:  # network / service refusals
            last = f"{e.__class__.__name__}: {str(e)[:150]}"
    raise VoiceError(f"edge-tts failed: {last}")


def synth(text, cfg, out_path):
    if (cfg.get("voice") or {}).get("provider", "edge") == "edge":
        return synth_edge(text, cfg, out_path)
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("ELEVENLABS_API_KEY is not set")
    v = cfg["voice"]
    url = f"{API}/v1/text-to-speech/{v['voice_id']}"
    body = {
        "text": text,
        "model_id": v.get("model_id", "eleven_multilingual_v2"),
        "voice_settings": v.get("voice_settings", {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}),
    }
    try:
        r = requests.post(url, params={"output_format": "mp3_44100_128"}, json=body,
                          headers={"xi-api-key": key, "Accept": "audio/mpeg"}, timeout=90)
    except requests.RequestException as e:
        raise VoiceError(f"network error: {e.__class__.__name__}")
    if r.status_code != 200:
        # never echo the key; the response body of ElevenLabs holds only an error message
        raise VoiceError(f"ElevenLabs HTTP {r.status_code}: {r.text[:300]}")
    with open(out_path, "wb") as fh:
        fh.write(r.content)
    return out_path


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def make_clips(product, script, cfg, workdir, stem):
    """Returns (paths_or_None list per scene, chars_used). Raises VoiceError."""
    lines = speech_lines(product, script, cfg)
    paths, chars = [], 0
    for i, line in enumerate(lines):
        p = os.path.join(workdir, f"{stem}-v{i}.mp3")
        synth(line, cfg, p)
        chars += len(line)
        paths.append(p)
    return paths, chars
