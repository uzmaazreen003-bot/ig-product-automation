"""Natural sound effects (typing, pops, whoosh, coins) and the final audio mix. No music."""
import subprocess
import wave

import numpy as np

SR = 44100
_rng = np.random.default_rng(11)


def snd_key():
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    noise = np.diff(_rng.standard_normal(n + 1))
    env = np.exp(-t * _rng.uniform(260, 360))
    thump = np.sin(2 * np.pi * _rng.uniform(900, 1300) * t) * np.exp(-t * 120) * 0.5
    return (noise * env * 0.35 + thump * 0.3) * _rng.uniform(0.7, 1.0)


def snd_pop(f0=520, f1=1100):
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * np.minimum(t / 0.09, 1)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 30) * 0.5


def snd_whoosh(dur=0.4):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.convolve(_rng.standard_normal(n), np.ones(24) / 24, mode="same")
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return noise * env * 0.35


def snd_ding():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 6) * 0.3 +
            np.sin(2 * np.pi * 1980 * t) * np.exp(-t * 9) * 0.15)


def snd_coin():
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    a = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 28)
    b = np.sin(2 * np.pi * 3100 * t) * np.exp(-(t - 0.06).clip(0) * 24) * (t > 0.06)
    return (a + b) * 0.26


def snd_tick():
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 160) * 0.18


def _bank():
    return {
        "key": [snd_key() for _ in range(8)],
        "pop": [snd_pop(520, 1100)],
        "pop2": [snd_pop(700, 1500)],
        "ding": [snd_ding()],
        "coin": [snd_coin()],
        "whoosh": [snd_whoosh(0.4)],
        "tick": [snd_tick()],
    }


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def mix_audio(voice_items, events, total, out_wav):
    """voice_items: [(mp3 path, start_sec)], events: [(t_sec, kind, gain)]"""
    n = int((total + 0.5) * SR)
    voice = np.zeros(n, np.float32)
    for path, start in voice_items:
        a = load_audio(path)
        i = int(start * SR)
        j = min(n, i + len(a))
        if i < n:
            voice[i:j] += a[: j - i]
    pk = float(np.max(np.abs(voice))) or 1.0
    voice = voice / pk * 0.85

    bank = _bank()
    rnd = np.random.default_rng(5)
    fx = np.zeros(n, np.float32)
    for t, kind, gain in events:
        snds = bank.get(kind)
        if not snds:
            continue
        s = snds[int(rnd.integers(0, len(snds)))].astype(np.float32)
        i = int(t * SR)
        if i < 0 or i >= n:
            continue
        j = min(n, i + len(s))
        fx[i:j] += s[: j - i] * gain
    fx = np.clip(fx, -1, 1) * 0.55
    mixed = np.clip(voice + fx, -1, 1)
    pcm = (mixed * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
