"""Cards: the text layer of each beat, drawn as HTML, plus one caption image per spoken word.

Each format has its own layout. Vertical follows the Reels/TikTok safe zones (content above y≈1290,
captions at y≈1345, the right edge clear of the like/comment rail). Landscape puts headlines in a left
column next to the animation. Square stacks them. A card is either opaque (the theme's glowing
background) or transparent (over an animated scene or an image).
"""

from __future__ import annotations

import html
from pathlib import Path

from playwright.sync_api import Page

from . import formats, icons, themes
from .browser import shot
from .captions import chunks
from .spec import Beat, End, Hook, ListBeat, ListItem, Reel, SceneBeat, Stat, Text
from .workspace import FONTS

# Per-format layout: where the text zone, handle and captions sit, and how big type is.
LAYOUT = {
    "vertical": {"zone": "left:84px; right:200px; top:300px; bottom:640px;", "handle": "left:84px; top:150px;",
                 "caps": "left:140px; right:140px; top:1345px;", "scale": 1.0, "cap": 52,
                 "scene_zone": "left:84px; right:200px; top:200px; bottom:auto;", "scene_head": 76},
    "landscape": {"zone": "left:140px; right:140px; top:120px; bottom:230px;", "handle": "left:140px; top:64px;",
                  "caps": "left:300px; right:300px; top:905px;", "scale": 0.92, "cap": 48,
                  "scene_zone": "left:120px; right:1180px; top:120px; bottom:230px; justify-content:center;", "scene_head": 72},
    "square": {"zone": "left:80px; right:80px; top:130px; bottom:200px;", "handle": "left:80px; top:56px;",
               "caps": "left:90px; right:90px; top:960px;", "scale": 0.78, "cap": 42,
               "scene_zone": "left:80px; right:80px; top:104px; bottom:auto;", "scene_head": 54},
}


def _css(reel: Reel) -> str:
    t = themes.get(reel.theme, reel.accent)
    fmt = formats.get(reel.format)
    lay = LAYOUT[fmt.name]
    f = FONTS.as_uri()
    family = "Mono, Inter" if reel.font == "mono" else "Inter"
    grad = f"linear-gradient(92deg,{t['accent']} 0%,{t['accent2']} 55%,{t['accent3']} 100%)"
    return f"""
@font-face {{ font-family: Inter; font-weight: 400; src: url({f}/Inter-Regular.ttf); }}
@font-face {{ font-family: Inter; font-weight: 600; src: url({f}/Inter-SemiBold.ttf); }}
@font-face {{ font-family: Inter; font-weight: 700; src: url({f}/Inter-Bold.ttf); }}
@font-face {{ font-family: Mono; font-weight: 400; src: url({f}/JetBrainsMono-Regular.ttf); }}
@font-face {{ font-family: Mono; font-weight: 700; src: url({f}/JetBrainsMono-SemiBold.ttf); }}
* {{ margin:0; box-sizing:border-box; }}
body {{ width:{fmt.w}px; height:{fmt.h}px; overflow:hidden; font-family:{family},'Apple Color Emoji','Noto Color Emoji';
  color:{t['text']}; -webkit-font-smoothing:antialiased; }}
.bg {{ position:absolute; inset:0; }}
.handle {{ position:absolute; {lay['handle']} font-weight:600; font-size:30px; letter-spacing:0.02em; color:{t['mute']}; }}
.zone {{ position:absolute; {lay['zone']} display:flex; flex-direction:column; justify-content:center; gap:28px; }}
.h {{ font-weight:700; letter-spacing:{'-0.02em' if reel.font == 'mono' else '-0.045em'}; line-height:1.05; }}
.sub {{ font-weight:400; font-size:44px; line-height:1.3; color:{t['mute']}; letter-spacing:-0.01em; }}
.eyebrow {{ font-weight:600; font-size:30px; letter-spacing:0.14em; text-transform:uppercase; color:{t['accent']}; }}
.grad {{ background:{grad}; -webkit-background-clip:text; color:transparent; }}
.head {{ font-weight:700; letter-spacing:-0.04em; line-height:1.05; }}
.row {{ display:flex; align-items:center; gap:26px; border-radius:30px; background:{t['surface']};
  border:2px solid {t['line']}; padding:24px 30px; font-weight:700; font-size:48px; letter-spacing:-0.03em; }}
.hide {{ visibility:hidden; }}
.tile {{ flex:none; display:inline-flex; align-items:center; justify-content:center;
  background:linear-gradient(135deg,{t['accent']},{t['accent2']}); box-shadow:0 10px 30px rgba(0,0,0,0.25),
  inset 0 1px 0 rgba(255,255,255,0.25); }}
.caps {{ position:absolute; {lay['caps']} display:flex; justify-content:center; }}
.cap {{ font-weight:700; font-size:{lay['cap']}px; letter-spacing:-0.02em; line-height:1.25; text-align:center;
  color:{t['captext']}; text-shadow:{t['capshadow']}; }}
.cap .w {{ display:inline-block; margin:0 5px; opacity:0.88; }}
.cap.highlight .on {{ opacity:1; color:transparent; background:{grad}; -webkit-background-clip:text; text-shadow:none;
  transform:scale(1.08); filter:drop-shadow(0 0 18px rgba(143,160,255,0.45)) drop-shadow(0 3px 10px rgba(0,0,0,0.5)); }}
.cap.box .on {{ opacity:1; background:{t['accent']}; color:{t['bg']}; text-shadow:none; border-radius:12px;
  padding:0 12px; transform:rotate(-1.5deg) scale(1.04); }}
.cap.minimal .w {{ opacity:0.55; font-weight:600; }}
.cap.minimal .on {{ opacity:1; }}
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _size(text: str, scale: float, big: int = 132) -> int:
    """Headline size steps down with length so every line fits in two or three rows."""
    n = len(text)
    px = big + 20 if n <= 14 else big if n <= 24 else big - 18 if n <= 36 else big - 30
    return round(px * scale)


def _tile(name: str, px: int = 108) -> str:
    return (f'<span class="tile" style="width:{px}px;height:{px}px;border-radius:{px * 0.28:.0f}px">'
            f'{icons.svg(name, int(px * 0.52))}</span>')


def steps(b: Beat) -> int:
    """How many build states a beat has (lists reveal one item at a time)."""
    return len(b.items) if isinstance(b, ListBeat) else 1


def _body(b: Beat, step: int, reel: Reel) -> str:
    s = LAYOUT[formats.get(reel.format).name]["scale"]
    if isinstance(b, Hook):
        eyebrow = f'<div class="eyebrow">{_esc(b.eyebrow)}</div>' if b.eyebrow else ""
        return f'{eyebrow}<div class="h" style="font-size:{_size(b.text, s, 140)}px">{_esc(b.text)}</div>'
    if isinstance(b, Text):
        icon = f'<div style="margin-bottom:6px">{_tile(b.icon, round(132 * s))}</div>' if b.icon else ""
        sub = f'<div class="sub">{_esc(b.sub)}</div>' if b.sub else ""
        return f'{icon}<div class="h" style="font-size:{_size(b.text, s)}px">{_esc(b.text)}</div>{sub}'
    if isinstance(b, Stat):
        icon = f'<div style="margin-bottom:6px">{_tile(b.icon, round(120 * s))}</div>' if b.icon else ""
        big = round((220 if len(b.value) <= 5 else 170) * s)
        return (f'{icon}<div class="h grad" style="font-size:{big}px">{_esc(b.value)}</div>'
                f'<div class="sub" style="font-size:{round(52 * s)}px">{_esc(b.label)}</div>')
    if isinstance(b, ListBeat):
        head = f'<div class="head" style="font-size:{round(72 * s)}px">{_esc(b.head)}</div>' if b.head else ""
        rows = []
        for i, it in enumerate(b.items):
            assert isinstance(it, ListItem)
            lead = _tile(it.icon, 76) if it.icon else ""
            rows.append(f'<div class="row{"" if i < step else " hide"}">{lead}<span>{_esc(it.text)}</span></div>')
        return f'{head}<div style="display:flex;flex-direction:column;gap:22px">{"".join(rows)}</div>'
    if isinstance(b, SceneBeat):
        px = LAYOUT[formats.get(reel.format).name]["scene_head"]
        return f'<div class="head" style="font-size:{px}px">{_esc(b.head)}</div>' if b.head else ""
    if isinstance(b, End):
        who = f'<div class="h grad" style="font-size:{round(118 * s)}px">{_esc(reel.handle)}</div>' if reel.handle else ""
        return f'{who}<div class="h" style="font-size:{round(68 * s)}px">{_esc(b.text)}</div>'
    raise TypeError(f"unknown beat {b!r}")


def layered(b: Beat) -> bool:
    return isinstance(b, SceneBeat) or bool(getattr(b, "background", None))


def _scrim(reel: Reel, b: Beat) -> tuple[str, str]:
    """(background element, extra CSS) for a card laid over a scene or image."""
    t = themes.get(reel.theme, reel.accent)
    fmt = formats.get(reel.format).name
    bg = t["bg"]
    solid = "rgba(246,243,236,{a})" if t["light"] == "1" else "rgba(5,6,10,{a})"
    shadow = "" if t["light"] == "1" else " .h,.head{text-shadow:0 4px 28px rgba(0,0,0,0.7)}"
    if isinstance(b, SceneBeat):
        lay = LAYOUT[fmt]["scene_zone"]
        if fmt == "landscape":
            grad = f"linear-gradient(90deg, {solid.format(a=0.92)} 0%, {solid.format(a=0.6)} 30%, {solid.format(a=0)} 42%)"
        else:
            stop = "22%" if fmt == "vertical" else "20%"
            grad = f"linear-gradient(180deg, {solid.format(a=0.92)} 0%, {solid.format(a=0.55)} 13%, {solid.format(a=0)} {stop})"
        return (f'<div class="bg" style="background:{grad}"></div>',
                f"body{{background:transparent}}{shadow} .zone{{{lay} justify-content:flex-start}}"
                + (" .zone{justify-content:center}" if fmt == "landscape" else ""))
    # Hook/text over a background: the picture shows, the text sits on a dark (or light) band.
    if fmt == "landscape":
        grad = f"linear-gradient(90deg, {solid.format(a=0.94)} 0%, {solid.format(a=0.85)} 38%, {solid.format(a=0.1)} 62%)"
        zone = ".zone{right:900px}"
    elif fmt == "square":
        grad = f"linear-gradient(180deg, {solid.format(a=0.1)} 0%, {solid.format(a=0.1)} 48%, {solid.format(a=0.9)} 58%, {bg} 100%)"
        zone = ".zone{top:560px; justify-content:flex-end}"
    else:
        stops = [(0.15, 0), (0.10, 37), (0.88, 43), (0.94, 100)]
        grad = "linear-gradient(180deg, " + ", ".join(f"{solid.format(a=a)} {pos}%" for a, pos in stops) + ")"
        zone = ".zone{justify-content:flex-end;gap:20px} .zone .h{font-size:92px !important;line-height:1.06}"
    return f'<div class="bg" style="background:{grad}"></div>', f"body{{background:transparent}}{shadow} {zone}"


def card_html(reel: Reel, b: Beat, step: int) -> str:
    t = themes.get(reel.theme, reel.accent)
    if layered(b):
        back, extra = _scrim(reel, b)
    else:
        back = (f'<div class="bg" style="background:radial-gradient(760px 760px at 18% 16%, {t["glow1"]}, transparent 62%), '
                f'radial-gradient(700px 700px at 90% 88%, {t["glow2"]}, transparent 60%), {t["bg"]}"></div>')
        extra = ""
    handle = f'<div class="handle">{_esc(reel.handle)}</div>' if reel.handle else ""
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_css(reel)}{extra}</style></head>'
            f'<body>{back}{handle}<div class="zone">{_body(b, step, reel)}</div></body></html>')


def caption_html(reel: Reel, words: list[str], on: int) -> str:
    line = " ".join(f'<span class="w{" on" if i == on else ""}">{_esc(w)}</span>' for i, w in enumerate(words))
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_css(reel)}body{{background:transparent}}</style>'
            f'</head><body><div class="caps"><div class="cap {reel.captions}">{line}</div></div></body></html>')


def render_beat(p: Page, reel: Reel, k: int, out: Path) -> tuple[list[Path], list[list[Path]]]:
    """Writes beat k's card states and caption images. Returns (states, captions[chunk][word])."""
    b = reel.beats[k]
    states = []
    for s in range(1, steps(b) + 1):
        f = out / f"{k:02d}_card_{s:02d}.png"
        shot(p, card_html(reel, b, s), f, transparent=layered(b))
        states.append(f)
    caps: list[list[Path]] = []
    if reel.captions == "none":
        return states, caps
    for g, ws in enumerate(chunks(b.say)):
        row = []
        for w in range(len(ws)):
            f = out / f"{k:02d}_cap_{g:02d}_{w:02d}.png"
            shot(p, caption_html(reel, ws, w), f, transparent=True)
            row.append(f)
        caps.append(row)
    return states, caps
