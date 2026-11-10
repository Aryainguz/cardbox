"""Color themes. Cards, captions and scenes all read their colors from here, so a video restyles with one
field. `accent` in the spec overrides a theme's main accent color.
"""

from __future__ import annotations

import re

_DARK = {"surface": "rgba(14,17,26,0.92)", "line": "rgba(255,255,255,0.10)", "grid": "rgba(255,255,255,0.035)",
         "captext": "#FFFFFF", "capshadow": "0 3px 18px rgba(0,0,0,0.85), 0 1px 3px rgba(0,0,0,0.9)", "light": "0"}

THEMES: dict[str, dict[str, str]] = {
    "midnight": {**_DARK, "bg": "#05060A", "glow1": "rgba(76,141,255,0.26)", "glow2": "rgba(167,139,250,0.18)",
                 "accent": "#7CB0FF", "accent2": "#A78BFA", "accent3": "#FF9F7A", "text": "#F5F5F7", "mute": "#A1A1AA"},
    "ember": {**_DARK, "bg": "#0A0506", "glow1": "rgba(255,72,72,0.28)", "glow2": "rgba(255,159,122,0.16)",
              "accent": "#FF7A6B", "accent2": "#FBBF24", "accent3": "#FF4D7D", "text": "#F7F5F5", "mute": "#B4A7A7"},
    "forest": {**_DARK, "bg": "#040806", "glow1": "rgba(30,215,96,0.22)", "glow2": "rgba(34,195,166,0.16)",
               "accent": "#34D399", "accent2": "#22C3A6", "accent3": "#A3E635", "text": "#F4F7F5", "mute": "#A0ADA6"},
    "neon": {**_DARK, "bg": "#07020F", "glow1": "rgba(236,72,153,0.28)", "glow2": "rgba(34,211,238,0.22)",
             "accent": "#F472B6", "accent2": "#22D3EE", "accent3": "#A78BFA", "text": "#FDF4FF", "mute": "#B9A9C9"},
    "sunset": {**_DARK, "bg": "#0C0607", "glow1": "rgba(251,146,60,0.28)", "glow2": "rgba(244,63,94,0.20)",
               "accent": "#FB923C", "accent2": "#F43F5E", "accent3": "#FACC15", "text": "#FFF7ED", "mute": "#C4A99B"},
    "mono": {**_DARK, "bg": "#060606", "glow1": "rgba(255,255,255,0.10)", "glow2": "rgba(255,255,255,0.06)",
             "accent": "#FFFFFF", "accent2": "#D4D4D8", "accent3": "#A1A1AA", "text": "#FAFAFA", "mute": "#A1A1AA"},
    "paper": {"bg": "#F6F3EC", "glow1": "rgba(255,190,120,0.30)", "glow2": "rgba(120,160,255,0.20)", "accent": "#2563EB",
              "accent2": "#7C3AED", "accent3": "#EA580C", "text": "#16161A", "mute": "#5B5B66",
              "surface": "rgba(255,255,255,0.94)", "line": "rgba(0,0,0,0.10)", "grid": "rgba(0,0,0,0.045)",
              "captext": "#16161A", "capshadow": "0 2px 14px rgba(255,255,255,0.9)", "light": "1"},
}

# Status colors for diagrams: deeper on light themes so they keep their contrast.
STATUS_LIGHT = {"green": "#16A34A", "red": "#DC2626", "amber": "#D97706", "blue": "#2563EB", "violet": "#7C3AED"}
STATUS_DARK = {"green": "#34D399", "red": "#FF5C5C", "amber": "#FBBF24", "blue": "#7CB0FF", "violet": "#A78BFA"}

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def get(name: str, accent: str | None = None) -> dict[str, str]:
    """The theme's palette plus status colors, with an optional accent override."""
    t = dict(THEMES.get(name, THEMES["midnight"]))
    t |= STATUS_LIGHT if t["light"] == "1" else STATUS_DARK
    if accent and HEX.match(accent):
        t["accent"] = accent
    return t
