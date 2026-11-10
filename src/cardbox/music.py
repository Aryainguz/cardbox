"""A generated music bed, so every video has a soundtrack with no licensing questions.

A kick on each beat, hats, a pad cycling through four chords, and a low hit on every cut so scene
changes land. Three moods: calm (default), upbeat (faster, major, busier hats) and tense (slow, minor,
a low drone, no hats). Written straight to a WAV with numpy.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
# Chord loops as the three note frequencies (Hz) of each chord.
MINOR = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (130.81, 164.81, 196.00), (196.00, 246.94, 293.66)]
MAJOR = [(261.63, 329.63, 392.00), (196.00, 246.94, 293.66), (220.00, 261.63, 329.63), (174.61, 220.00, 261.63)]
DARK = [(220.00, 261.63, 329.63), (233.08, 277.18, 349.23), (220.00, 261.63, 329.63), (207.65, 246.94, 311.13)]
MOODS = {
    "calm": {"bpm": 96, "chords": MINOR, "hats": 2, "kick": 0.55, "pad": 0.05, "drone": 0.0},
    "upbeat": {"bpm": 118, "chords": MAJOR, "hats": 4, "kick": 0.6, "pad": 0.045, "drone": 0.0},
    "tense": {"bpm": 84, "chords": DARK, "hats": 0, "kick": 0.45, "pad": 0.04, "drone": 0.05},
}
CHORDS = MINOR


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(np.clip(t / max(attack, 1e-4), 0, 1), np.exp(-t / max(release, 1e-4)))


def bed(seconds: float, cuts: list[float], mood: str = "calm", seed: int = 7) -> np.ndarray:
    """Stereo float32 samples in [-1, 1]."""
    m = MOODS.get(mood, MOODS["calm"])
    n = int(SR * seconds)
    out = np.zeros(n, dtype=np.float64)
    t = np.arange(n) / SR
    beat = 60.0 / m["bpm"]
    rng = np.random.default_rng(seed)

    kick_len = int(0.35 * SR)
    kt = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * (48 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    hat_len = int(0.05 * SR)
    hat = rng.standard_normal(hat_len) * np.exp(-np.arange(hat_len) / SR * 90)
    hat = np.diff(hat, prepend=0.0)  # crude high-pass: keep it airy

    def place(sample: np.ndarray, at: float, gain: float) -> None:
        a = int(at * SR)
        if a >= n:
            return
        b = min(n, a + len(sample))
        out[a:b] += gain * sample[: b - a]

    k = 0.0
    while k < seconds:
        place(kick, k, m["kick"])
        for h in range(m["hats"]):  # 2: off-beats, 4: sixteenths
            if m["hats"] == 2 and h % 2 == 0:
                continue
            place(hat, k + beat * h / max(m["hats"], 1), 0.08 if h % 2 else 0.05)
        k += beat

    bar = beat * 4
    for i, start in enumerate(np.arange(0, seconds, bar)):
        chord = m["chords"][i % len(m["chords"])]
        a, b = int(start * SR), min(n, int((start + bar) * SR))
        seg = t[a:b] - start
        env = np.minimum(np.clip(seg / 0.4, 0, 1), np.clip((bar - seg) / 0.6, 0, 1))
        tone = sum(np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * 2 * f * seg) for f in chord)
        out[a:b] += m["pad"] * env * tone

    if m["drone"]:
        out += m["drone"] * np.sin(2 * np.pi * 55 * t) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.11 * t))

    hit_len = int(0.9 * SR)
    ht = np.arange(hit_len) / SR
    hit = np.sin(2 * np.pi * 55 * ht) * _env(hit_len, 0.005, 0.35)
    for c in cuts:
        place(hit, c, 0.35)

    fade = min(n, int(1.5 * SR))
    out[-fade:] *= np.linspace(1, 0, fade)
    out /= max(1e-6, np.abs(out).max()) / 0.8
    stereo = np.stack([out, np.roll(out, int(0.012 * SR))], axis=1)
    return stereo.astype(np.float32)


def write(path: Path, samples: np.ndarray) -> Path:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path
