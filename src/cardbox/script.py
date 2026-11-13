"""Plain-text scripts: write what you want to say, get a video. No YAML.

    One step. Any size.
    Your phone finds one contact out of ten thousand in a single step.

    # 1 million checks
    Checking names one by one gets slower as the list grows.

    Follow for more computer science, explained simply.

Rules:
- Paragraphs (separated by blank lines) are beats. The text is what gets spoken.
- A line starting with `# ` sets the beat's on-screen headline. Without one, the headline is the
  paragraph's first sentence, shortened.
- A headline that leads with a number ("8.8%", "₹615 crore", "265 ms") becomes a big stat card.
- The first paragraph is the hook, the last is the closing card.
- Media: drop images or video clips in the video's `media/` folder. A line `@ city.mp4` in a paragraph
  puts that file behind the beat; files named by beat number (`1.jpg`, `02.mp4`) are used automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

from .spec import Background, End, Hook, Reel, Stat, Text

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}

# A leading number with an optional unit. Longer units are tried first ("million" before "m"), and the
# unit must end the word, so "1 million checks" → "1 million" and "8.8% of the music" → "8.8%".
NUMBER = re.compile(r"^[₹$€£¥]?\d[\d.,]*(?:\s?(?:million|billion|crore|lakh|ms|kb|mb|gb|tb|bn|km|%|x|s|k|m))?(?=\s|$)", re.I)
MAX_WORDS = 7


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]


def headline(spoken: str) -> str:
    """A short on-screen line from a spoken paragraph: its first sentence, or its first clause, or
    its first few words."""
    first = _sentences(spoken)[0] if spoken.strip() else ""
    words = first.split()
    if len(words) <= MAX_WORDS:
        return first.rstrip(".")
    clause = re.split(r"[,:;—–]\s", first)[0]
    if len(clause.split()) <= MAX_WORDS:
        return clause.rstrip(".")
    return " ".join(words[:6]).rstrip(",.;:") + "…"


def _blocks(text: str) -> list[tuple[str | None, str, str | None]]:
    """(explicit headline or None, spoken text, media file or None) per paragraph."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.strip().splitlines() if ln.strip()]
        head = media = None
        rest = []
        for ln in lines:
            if ln.startswith("# ") and head is None and not rest:
                head = ln[2:].strip()
            elif ln.startswith("@"):
                media = ln[1:].strip()
            else:
                rest.append(ln)
        spoken = " ".join(rest).strip()
        if spoken:
            out.append((head, spoken, media))
    return out


def numbered_media(folder: Path | None) -> dict[int, str]:
    """{beat number (1-based): file name} for media files named by number: 1.jpg, 02.mp4, 3-city.mov."""
    found: dict[int, str] = {}
    if folder and folder.is_dir():
        for f in sorted(folder.iterdir()):
            m = re.match(r"^(\d+)(?:[-_ ].*)?$", f.stem)
            if m and f.suffix.lower() in IMAGE_EXT | VIDEO_EXT:
                found.setdefault(int(m.group(1)), f.name)
    return found


def _background(name: str) -> Background:
    path = name if "/" in name else f"media/{name}"
    return Background(video=path) if Path(name).suffix.lower() in VIDEO_EXT else Background(image=path)


def from_text(text: str, title: str = "", media_dir: Path | None = None, **options: object) -> Reel:
    """Turns a plain-text script into a video spec. `media_dir` is the video's media folder (for
    numbered files); `options` are top-level spec fields (format, theme, voice, handle, music, ...)."""
    blocks = _blocks(text)
    if len(blocks) < 2:
        raise ValueError("write at least two paragraphs (separated by a blank line): a hook and an ending")
    auto = numbered_media(media_dir)
    beats = []
    for i, (head, spoken, media) in enumerate(blocks):
        shown = head or headline(spoken)
        file = media or auto.get(i + 1)
        bg = _background(file) if file else None
        if i == 0:
            beats.append(Hook(text=shown, say=spoken, background=bg))
        elif i == len(blocks) - 1:
            beats.append(End(text=shown, say=spoken))
        elif head and (m := NUMBER.match(head)) and m.group(0).strip() and not bg:  # only explicit "# 8.8% ..." headlines
            value = m.group(0).strip()
            label = shown[len(m.group(0)):].strip()  # "# 265 ms to start a song" → label "to start a song"
            beats.append(Stat(value=value, label=label, say=spoken))
        else:
            beats.append(Text(text=shown, say=spoken, background=bg))
    return Reel(title=title or beats[0].text, beats=beats, **options)  # type: ignore[arg-type]
