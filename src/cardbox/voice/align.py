"""Maps what the speech recognizer heard onto the script's words, so captions highlight the right
word at the right time, and scenes can cue on words.

Recognizers hear "2010" for "twenty ten" or "Song's PK" for "SongsPK". Words that match get their
heard times; the rest are interpolated between their matched neighbours, weighted by length.
"""

from __future__ import annotations

import difflib
import re

Heard = tuple[str, float, float]


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def map_words(script: list[str], heard: list[Heard], duration: float) -> list[tuple[float, float]]:
    """(start, end) for every script word. `heard` is [(word, start, end)] from the recognizer."""
    if not script:
        return []
    times: list[tuple[float, float] | None] = [None] * len(script)
    a, b = [norm(w) for w in script], [norm(h[0]) for h in heard]
    for blk in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            _, s, e = heard[blk.b + k]
            times[blk.a + k] = (s, e)
    i = 0
    while i < len(script):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(script) and times[j] is None:
            j += 1
        start = times[i - 1][1] if i > 0 and times[i - 1] else 0.0
        end = times[j][0] if j < len(script) and times[j] else duration
        end = max(end, start + 0.05 * (j - i))
        weights = [len(script[k]) + 1 for k in range(i, j)]
        t, total = start, sum(weights)
        for k, w in zip(range(i, j), weights):
            span = (end - start) * w / total
            times[k] = (t, end if k == j - 1 else t + span)  # the last word ends exactly at `end`
            t += span
        i = j
    return [t for t in times if t is not None]


_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if i > 1}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}


def numbers_to_digits(tokens: list[str]) -> list[str]:
    """Rewrites spelled-out numbers as digits ("ten thousand" → "10000"), as speech recognizers write
    them, so a correct take isn't marked wrong for spelling a number differently."""
    out: list[str] = []
    total = current = 0
    in_number = False
    for t in tokens + [""]:
        parts = t.split("-") if "-" in t else [t]
        if t and all(p in _UNITS or p in _TENS or p in _SCALES for p in parts):
            for p in parts:
                if p in _UNITS:
                    current += _UNITS[p]
                elif p in _TENS:
                    current += _TENS[p]
                elif p == "hundred":
                    current = max(current, 1) * 100
                else:
                    total += max(current, 1) * _SCALES[p]
                    current = 0
            in_number = True
            continue
        if in_number:
            out.append(str(total + current))
            total = current = 0
            in_number = False
        if t:
            out.append(t)
    return out


def match_score(expected: str, heard: str) -> float:
    """How closely a transcript matches the script (0..1), ignoring case, punctuation and how
    numbers are written."""
    def tokens(text: str) -> list[str]:
        # Hyphens and run-together capitals are word breaks: "open-source" = "open source" and a
        # recognizer's "GoRender" = "Go render". Without this, correct takes get retried for nothing.
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).replace("-", " ")
        spoken = [w.lower().strip(",.?!:;\"'()") for w in text.split()]
        return [norm(w) for w in numbers_to_digits(spoken) if norm(w)]

    a, b = tokens(expected), tokens(heard)
    if not a:
        return 1.0
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()
