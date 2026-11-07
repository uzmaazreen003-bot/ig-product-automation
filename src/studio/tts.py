"""edge-tts Hindi narration, one mp3 per scene, with word timing when the service provides it."""
import asyncio
import os
import subprocess
import time

import base64
import requests

try:
    import edge_tts
except ImportError:  # only missing in offline tests
    edge_tts = None


async def _run(text, voice, rate, out):
    try:
        com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(text, voice, rate=rate)
    events = []
    with open(out, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                off, dur = ch["offset"] / 1e7, ch["duration"] / 1e7
                events.append((ch.get("text", ""), off, off + dur))
    return events


def synth(text, voice, rate, out, tries=5):
    last = None
    for i in range(tries):
        try:
            ev = asyncio.run(_run(text, voice, rate, out))
            if os.path.exists(out) and os.path.getsize(out) > 2000:
                return ev
            last = "empty audio"
        except Exception as e:  # noqa: BLE001
            last = e
        print(f"  tts retry {i + 1}: {last}")
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"TTS failed: {last}")


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def synth_gemini(text, voice, models, style, out, tries=4):
    """Gemini TTS (expressive). Returns [] (no word timings; timeline estimates them)."""
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": [{"text": f"{style}:\n\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    last = None
    for i in range(tries):
        for m in models:
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                  headers={"x-goog-api-key": key}, json=body, timeout=240)
                if r.status_code == 200:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    b64 = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
                    pcm = base64.b64decode(b64)
                    if len(pcm) < 8000:
                        raise ValueError("audio too short")
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "-",
                                    "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                                           "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                                    "-b:a", "128k", out], input=pcm, check=True)
                    return []
                last = f"{m}: {r.status_code} {r.text[:160]}"
            except Exception as e:  # noqa: BLE001
                last = f"{m}: {e}"
        print(f"  gemini tts retry {i + 1}: {last}")
        time.sleep(12 * (i + 1))
    raise RuntimeError(f"Gemini TTS failed: {last}")
