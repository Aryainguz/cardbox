"""Caption chunking and timing.

Captions show a few words at a time with the spoken word highlighted. Chunks break after punctuation,
lone words are folded into a neighbour (they flash by too fast to read), and exactly one caption is on
screen at any moment even when word timings overlap.
"""

from __future__ import annotations

import re

PUNCT_END = re.compile(r"[.,?!:;…]$")


def words(line: str) -> list[str]:
    """The caption words of a spoken line, in the same split every other step uses."""
    return line.replace("...", "…").split()


def chunks(line: str, size: int = 4) -> list[list[str]]:
    """Splits a line into caption chunks of up to `size` words, breaking after punctuation."""
    out: list[list[str]] = []
    cur: list[str] = []
    for w in words(line):
        cur.append(w)
        if len(cur) >= size or PUNCT_END.search(w):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    merged: list[list[str]] = []
    for c in out:
        if merged and (len(c) == 1 or len(merged[-1]) == 1) and len(merged[-1]) + len(c) <= size + 2:
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    return merged


def estimate_seconds(line: str) -> float:
    """Speaking time for a line with no voice take (silent previews)."""
    return 0.6 + 0.34 * len(words(line))


def spread(line: str, seconds: float) -> list[tuple[float, float]]:
    """(start, end) per word when there is no alignment: spread across the line by word length."""
    ws = words(line)
    weights = [len(w) + 1 for w in ws]
    total = sum(weights) or 1
    out, t = [], 0.0
    for w in weights:
        span = seconds * w / total
        out.append((t, t + span))
        t += span
    return out


def schedule(
    groups: list[list[str]], times: list[tuple[float, float]], lead: float = 0.0, tail: float = 0.12
) -> list[tuple[int, int, float, float]]:
    """One entry per spoken word: (chunk index, word index, start, end), never overlapping.

    `times` holds (start, end) per word across all chunks, relative to the line's start; `lead` is
    silence before the line. Within a chunk a word's caption lasts until the next word starts; the
    chunk's last word lingers for `tail` seconds.
    """
    flat = [(g, w) for g, ws in enumerate(groups) for w in range(len(ws))]
    if len(flat) != len(times):
        raise ValueError(f"{len(flat)} caption words but {len(times)} timings")
    out: list[tuple[int, int, float, float]] = []
    for i, (g, w) in enumerate(flat):
        start = lead + times[i][0]
        same_chunk_next = i + 1 < len(flat) and flat[i + 1][0] == g
        end = lead + (times[i + 1][0] if same_chunk_next else times[i][1] + tail)
        out.append((g, w, start, max(end, start + 0.08)))
    for i in range(len(out) - 1):
        g, w, a, b = out[i]
        ng, nw, na, nb = out[i + 1]
        if na <= a:
            na = a + 0.08
            out[i + 1] = (ng, nw, na, max(nb, na + 0.08))
        out[i] = (g, w, a, min(b, na - 0.001))
    return out
