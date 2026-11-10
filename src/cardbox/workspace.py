"""Where things live on disk.

    $CARDBOX_HOME (default ~/Cardbox)
      reels/<name>/reel.yaml      the spec
      reels/<name>/media/         images used by the reel (+ credits.json)
      reels/<name>/build/         intermediate files (safe to delete)
      reels/<name>/<name>.mp4     the finished video, next to caption.txt
      voices/<voice>/takes/       your recorded takes, voices/<voice>/reference.wav
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ASSETS = PACKAGE / "assets"
FONTS = ASSETS / "fonts"
SCENES = PACKAGE / "scenes"
TEMPLATES = PACKAGE / "templates"


def home() -> Path:
    root = Path(os.environ.get("CARDBOX_HOME", Path.home() / "Cardbox")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def slug(name: str) -> str:
    """A safe folder name for a reel or voice: lowercase letters, digits and dashes."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s:
        raise ValueError(f"not a usable name: {name!r}")
    return s[:60]


def reel_dir(name: str) -> Path:
    d = home() / "reels" / slug(name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def voice_dir(name: str) -> Path:
    d = home() / "voices" / slug(name)
    (d / "takes").mkdir(parents=True, exist_ok=True)
    return d


def resolve_reel(ref: str) -> tuple[Path, Path]:
    """(spec file, reel folder) for a reel name or a path to a spec file."""
    p = Path(ref).expanduser()
    if p.suffix in {".yaml", ".yml", ".json"} and p.exists():
        p = p.resolve()
        return p, p.parent
    d = home() / "reels" / slug(ref)
    for f in ("reel.yaml", "reel.yml", "reel.json"):
        if (d / f).exists():
            return d / f, d
    raise FileNotFoundError(f"no reel named {ref!r} (looked in {d})")
