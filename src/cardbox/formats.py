"""Output formats. One spec renders to any of them.

Scenes are designed once, in a 1080-wide "stage" (the content band of a vertical video, y 330..1290).
Each format maps that stage onto its own frame: full width in vertical, the right side in landscape
(headline on the left), scaled into the middle in square. Cards and captions get per-format layouts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    name: str
    w: int
    h: int
    stage: tuple[float, float, float]  # where the design stage lands: x, y, scale
    full: tuple[int, int, int, int]  # the area a full-bleed background image covers
    use: str


FORMATS = {
    "vertical": Format("vertical", 1080, 1920, (0, 330, 1.0), (0, 0, 1080, 900),
                       "Reels, TikTok, YouTube Shorts, Stories"),
    "landscape": Format("landscape", 1920, 1080, (800, 70, 1.0), (0, 0, 1920, 1080),
                        "YouTube, LinkedIn, X, presentations"),
    "square": Format("square", 1080, 1080, (108, 190, 0.8), (0, 0, 1080, 620),
                     "LinkedIn and Instagram feed posts"),
}
ALIASES = {"reel": "vertical", "short": "vertical", "shorts": "vertical", "tiktok": "vertical", "portrait": "vertical",
           "youtube": "landscape", "wide": "landscape", "16:9": "landscape", "9:16": "vertical", "1:1": "square",
           "feed": "square"}


def get(name: str) -> Format:
    key = ALIASES.get(name, name)
    if key not in FORMATS:
        raise ValueError(f"unknown format {name!r}; use one of {', '.join(FORMATS)}")
    return FORMATS[key]
