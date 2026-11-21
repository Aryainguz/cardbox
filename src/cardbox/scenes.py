"""Renders animated scenes (canvas, in the headless browser) to video, frame by frame.

A scene is drawn at the beat's exact length, so its build-ups land on the spoken words: the page gets
the line's word timings and scenes can cue anything to a word.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from . import formats, icons, themes
from .browser import load_html
from .workspace import FONTS, SCENES

FPS = 30
LIBRARY = ("runtime.js", "library.js")

# One line per scene: what it's for and its params, handed to AI clients by the MCP server.
CATALOG = {
    "photo": "An image in a framed card pushing in slowly, or `full: true` across the top (for hook backgrounds). "
    "params: image, from [x,y,w], to [x,y,w] (fractions of the image), label {text,on,color}, stamp {text,on}",
    "donut": "Parts of a whole, swept in as they are said. params: segments [{label,value,color?,on?,display?}], "
    "center {value,label}, unit",
    "counter": "A number counting up to its value, optional ring and waveform. params: to, from, decimals, prefix, unit, "
    "label, ring, max, on, seconds, play (true or text), alarm",
    "bars": "Comparison bars; one highlighted. params: bars [{label,value,note?,on?}], unit, highlight",
    "mesh": "Peers passing data to each other; an optional hub fades as they take over. params: peers, hub, you, handoff, "
    "icon, hubIcon",
    "terminal": "Commands typing out in a terminal window. params: title, lines [{text,on?,color?,output?}]",
    "flow": "A vertical chain of steps with packets moving between them. params: nodes [{icon,label,sub?,on?,color?}], bad",
    "grid": "k of n icons lighting up (e.g. '1 in 10'). params: n, k, cols, icon, result {text,on}",
    "logo": "A logo reveal: an isometric box assembles, then a name and tagline. params: name, tagline, on",
    "chat": "A chat with typing dots before each reply. params: title, messages [{from: user|ai|<name>, text, on}], "
    "colors {name: color}. Named senders get a monogram avatar.",
    "script": "A text script whose paragraphs light up and turn into video frames. params: title, paragraphs [text], on [cues]",
    "voice": "A waveform and live transcript; one misheard word is caught and corrected. params: text, wrong {index, heard}, on",
    "formats": "One frame morphing between 9:16, 16:9 and 1:1. params: labels [3 strings], on [3 cues]",
    "alert": "An incident: red pulse, a push notification slides in, a latency chart spikes and glitches. params: app, channel, "
    "title, body, metric {label, from, to, unit}, on",
    "cards": "A challenge-card stack: timer ring, the answer line is tapped, a green sweep and check, then the next card. "
    "params: cards [{tag, question, code: [lines], answer, note, on}], seconds",
    "rings": "Activity rings closing one by one, then streak days lighting up. params: rings [{label, value, color}], days, "
    "streak, closed, on",
    "appreveal": "An app icon pops in with a light sweep, then its name, a tagline and a badge. params: image, name, tagline, "
    "badge, on",
}


def _scripts() -> str:
    return "\n".join((SCENES / f).read_text(encoding="utf-8") for f in LIBRARY)


def _images(params: Any, base: Path) -> dict[str, str]:
    """Every `image` param, resolved against the reel folder, as {name: file URL}."""
    found: dict[str, str] = {}

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, val in v.items():
                if k == "image" and isinstance(val, str):
                    p = (base / val).resolve() if not Path(val).is_absolute() else Path(val)
                    if not p.exists():
                        raise FileNotFoundError(f"image not found: {val} (looked for {p})")
                    found[val] = p.as_uri()
                else:
                    walk(val)
        elif isinstance(v, list):
            for i in v:
                walk(i)

    walk(params)
    return found


def page_html(scene: str, params: dict, style: dict, dur: float, voice: float, lead: float,
              words: list[tuple[str, float]], base: Path) -> str:
    """The scene page. `style` has theme, accent, font and format (as in the spec)."""
    if scene not in CATALOG:
        raise ValueError(f"unknown scene {scene!r}; available: {', '.join(CATALOG)}")
    code = _scripts()
    fmt = formats.get(style.get("format", "vertical"))
    config = {
        "scene": scene, "params": params, "theme": themes.get(style.get("theme", "midnight"), style.get("accent")),
        "format": {"name": fmt.name, "stage": fmt.stage, "full": fmt.full}, "font": style.get("font", "sans"),
        "dur": dur, "voice": voice, "lead": lead,
        "words": [[re.sub(r"[^a-z0-9]", "", w.lower()), s] for w, s in words],
        "icons": icons.subset(code + json.dumps(params)) | {"circle": icons.inner("circle")},
        "photos": _images(params, base),
    }
    f = FONTS.as_uri()
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; font-weight: 400; src: url({f}/Inter-Regular.ttf); }}
@font-face {{ font-family: Inter; font-weight: 600; src: url({f}/Inter-SemiBold.ttf); }}
@font-face {{ font-family: Inter; font-weight: 700; src: url({f}/Inter-Bold.ttf); }}
@font-face {{ font-family: Inter; font-weight: 800; src: url({f}/Inter-Bold.ttf); }}
@font-face {{ font-family: Mono; font-weight: 400; src: url({f}/JetBrainsMono-Regular.ttf); }}
@font-face {{ font-family: Mono; font-weight: 600; src: url({f}/JetBrainsMono-SemiBold.ttf); }}
@font-face {{ font-family: Mono; font-weight: 700; src: url({f}/JetBrainsMono-SemiBold.ttf); }}
@font-face {{ font-family: Mono; font-weight: 800; src: url({f}/JetBrainsMono-SemiBold.ttf); }}
html,body{{margin:0;background:#000}} canvas{{display:block}}</style></head>
<body><canvas id="c" width="{fmt.w}" height="{fmt.h}"></canvas>
<script>const CONFIG = {json.dumps(config)};</script><script>{code}</script></body></html>"""


def _prepare(p: Page, html: str, dur: float) -> None:
    load_html(p, html)
    p.evaluate("Promise.all(['400','600','700'].flatMap(w => ['Inter', 'Mono'].map(f => document.fonts.load(w + ' 40px ' + f))))")
    # Draw across the whole scene once so every icon image gets created, then wait for them all.
    p.evaluate("""async (dur) => { for (let t = 0; t <= dur; t += 0.25) window.drawAt(t);
                  await Promise.all(window.__loading || []); }""", dur)


def still(p: Page, html: str, dur: float, t: float, out: Path) -> Path:
    """One frame of a scene at time t, as PNG (for previews)."""
    _prepare(p, html, dur)
    p.evaluate("(t) => window.drawAt(t)", t)
    p.screenshot(path=str(out))
    return out


def render(p: Page, html: str, dur: float, out: Path) -> Path:
    """The whole scene as an H.264 clip of `dur` seconds."""
    _prepare(p, html, dur)
    frames = max(1, round(dur * FPS))
    with tempfile.TemporaryDirectory(prefix="cardbox-scene-") as tmp:
        for i in range(frames):
            p.evaluate("(t) => window.drawAt(t)", i / FPS)
            p.screenshot(path=f"{tmp}/{i:05d}.jpg", type="jpeg", quality=90)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/%05d.jpg",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out
