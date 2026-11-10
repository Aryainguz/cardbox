"""Voice profiles: a folder of your recorded takes, checked for quality, joined into one reference clip.

Cloning starts with consent. The first prompt is a consent statement in the speaker's own voice, and a
profile isn't usable until it has been recorded. Only clone voices you have the right to clone.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..workspace import home, slug, voice_dir

CONSENT = "This is my own voice, and I agree to it being cloned for videos I make."
# Prompts cover a wide range of sounds, rhythms and intonation (questions, numbers, emphasis) so the
# clone hears how you really speak. About a minute in total.
PROMPTS = [
    CONSENT,
    "Here's something most people never notice about the apps they use every single day.",
    "It started as a small experiment, and three years later it was running on millions of phones.",
    "Wait, what? You're telling me the whole thing ran on one tiny server in a basement?",
    "The numbers were wild: four hundred thousand requests a second, and not one of them failed.",
    "So why did it work? Because the engineers asked a better question than everyone else.",
    "Quick, fresh, and surprisingly cheap: that's the trick behind half of modern technology.",
    "If you remember just one thing from this video, remember that speed is a feature.",
    "Honestly? I didn't believe it either, until I read the original paper from twenty ten.",
    "Follow for more, and tell me in the comments which story I should explain next.",
]
MIN_TAKES = 4  # consent + three more is enough for a usable clone; all ten is better


@dataclass
class Quality:
    seconds: float
    peak_db: float
    level_db: float
    noise_db: float
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def decode(path: Path, rate: int = 16000) -> np.ndarray:
    """Any audio file → mono float32 samples, via ffmpeg."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(rate), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def assess(samples: np.ndarray, rate: int = 16000) -> Quality:
    """Checks a take: long enough, not clipped, loud enough, and quiet between words."""
    db = lambda v: float(20 * np.log10(max(v, 1e-9)))  # noqa: E731
    seconds = len(samples) / rate
    if len(samples) == 0:
        return Quality(0, -120, -120, -120, ["the recording is empty"])
    frame = int(0.05 * rate)
    n = max(1, len(samples) // frame)
    rms = np.sqrt(np.mean(samples[: n * frame].reshape(n, -1) ** 2, axis=1) + 1e-12)
    q = Quality(seconds=round(seconds, 2), peak_db=round(db(np.abs(samples).max()), 1),
                level_db=round(db(np.percentile(rms, 90)), 1), noise_db=round(db(np.percentile(rms, 10)), 1))
    if seconds < 2.0:
        q.issues.append("too short: read the whole sentence")
    if q.peak_db > -0.3:
        q.issues.append("clipping: move a little further from the mic")
    if q.level_db < -42:  # the reference is loudness-normalized later; only flag takes too quiet to hear
        q.issues.append("too quiet: move closer to the mic or raise its level")
    if q.level_db - q.noise_db < 18:
        q.issues.append("background noise: find a quieter room (a closet full of clothes works great)")
    return q


class Profile:
    """A voice profile on disk: takes/NN.wav, profile.json, reference.wav."""

    def __init__(self, name: str):
        self.name = slug(name)
        self.dir = voice_dir(self.name)
        self.meta_path = self.dir / "profile.json"

    @staticmethod
    def all() -> list[str]:
        root = home() / "voices"
        return sorted(p.name for p in root.iterdir() if (p / "takes").is_dir()) if root.exists() else []

    def meta(self) -> dict:
        return json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {"name": self.name}

    def take_path(self, i: int) -> Path:
        return self.dir / "takes" / f"{i:02d}.wav"

    def takes(self) -> list[Path]:
        return sorted((self.dir / "takes").glob("[0-9][0-9].wav"))

    @property
    def consented(self) -> bool:
        return self.take_path(0).exists() and bool(self.meta().get("consent"))

    def save_take(self, i: int, audio: Path) -> Quality:
        """Converts a recording to the take format (mono 24 kHz WAV) and checks it."""
        if not 0 <= i < len(PROMPTS):
            raise ValueError(f"prompt index out of range: {i}")
        out = self.take_path(i)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-ac", "1", "-ar", "24000", str(out)], check=True)
        q = assess(decode(out))
        meta = self.meta()
        meta.setdefault("takes", {})[f"{i:02d}"] = asdict(q) | {"ok": q.ok}
        if i == 0:
            meta |= {"consent": True, "consent_text": CONSENT, "consented_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        self.meta_path.write_text(json.dumps(meta, indent=2))
        (self.dir / "reference.wav").unlink(missing_ok=True)  # rebuilt on next use
        return q

    def status(self) -> dict:
        meta = self.meta().get("takes", {})
        done = [int(p.stem) for p in self.takes()]
        return {
            "voice": self.name, "consent": self.consented, "recorded": len(done), "needed": MIN_TAKES,
            "total_prompts": len(PROMPTS), "ready": self.consented and len(done) >= MIN_TAKES,
            "takes": {k: {"ok": v.get("ok"), "issues": v.get("issues", [])} for k, v in sorted(meta.items())},
            "next_prompt": next((i for i in range(len(PROMPTS)) if i not in done), None),
        }

    def reference(self) -> Path:
        """All good takes joined and levelled into one clip: what the cloning model listens to."""
        st = self.status()
        if not st["ready"]:
            raise RuntimeError(f"voice {self.name!r} isn't ready: record the consent line and at least "
                               f"{MIN_TAKES} takes first (`cardbox voice record {self.name}`)")
        ref = self.dir / "reference.wav"
        if ref.exists():
            return ref
        takes = self.takes()
        args = sum((["-i", str(t)] for t in takes), [])
        chain = "".join(f"[{i}:a]" for i in range(len(takes)))
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex",
                        f"{chain}concat=n={len(takes)}:v=0:a=1,highpass=f=70,loudnorm=I=-18:TP=-2[a]",
                        "-map", "[a]", "-ac", "1", "-ar", "24000", str(ref)], check=True)
        return ref
