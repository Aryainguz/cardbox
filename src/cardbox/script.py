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
"""

from __future__ import annotations

import re

from .spec import End, Hook, Reel, Stat, Text

NUMBER = re.compile(r"^[₹$€£¥]?\d[\d.,]*\s?(%|x|ms|s|k|m|bn|kb|mb|gb|tb|crore|lakh|million|billion|km|ms\b)?", re.I)
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


def _blocks(text: str) -> list[tuple[str | None, str]]:
    """(explicit headline or None, spoken text) per paragraph."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.strip().splitlines() if ln.strip()]
        head = None
        if lines and lines[0].startswith("# "):
            head = lines.pop(0)[2:].strip()
        spoken = " ".join(lines).strip()
        if spoken:
            out.append((head, spoken))
    return out


def from_text(text: str, title: str = "", **options: object) -> Reel:
    """Turns a plain-text script into a video spec. `options` are top-level spec fields
    (format, theme, voice, handle, music, captions, ...)."""
    blocks = _blocks(text)
    if len(blocks) < 2:
        raise ValueError("write at least two paragraphs (separated by a blank line): a hook and an ending")
    beats = []
    for i, (head, spoken) in enumerate(blocks):
        shown = head or headline(spoken)
        if i == 0:
            beats.append(Hook(text=shown, say=spoken))
        elif i == len(blocks) - 1:
            beats.append(End(text=shown, say=spoken))
        elif head and (m := NUMBER.match(head)) and m.group(0).strip():  # only explicit "# 8.8% ..." headlines
            value = m.group(0).strip()
            label = shown[len(m.group(0)):].strip()  # "# 265 ms to start a song" → label "to start a song"
            beats.append(Stat(value=value, label=label, say=spoken))
        else:
            beats.append(Text(text=shown, say=spoken))
    return Reel(title=title or beats[0].text, beats=beats, **options)  # type: ignore[arg-type]
