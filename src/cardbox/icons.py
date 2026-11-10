"""Lucide icons (ISC license, see assets/icons/LICENSE-lucide.txt), as inline SVG."""

from __future__ import annotations

import json
from functools import lru_cache

from .workspace import ASSETS

STROKE = 1.75


@lru_cache(maxsize=1)
def _all() -> dict[str, str]:
    return json.loads((ASSETS / "icons" / "lucide.json").read_text(encoding="utf-8"))


def exists(name: str) -> bool:
    return name in _all()


def names() -> list[str]:
    return sorted(_all())


def inner(name: str) -> str:
    """The icon's SVG body (paths, circles...), or a plain circle for unknown names."""
    return _all().get(name) or _all()["circle"]


def svg(name: str, px: int = 56, color: str = "#fff") -> str:
    return (
        f'<svg width="{px}" height="{px}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">{inner(name)}</svg>'
    )


def subset(text: str) -> dict[str, str]:
    """Every icon whose name appears quoted in `text` (scene code or params), for injecting into a page."""
    found = {}
    for name, body in _all().items():
        if f"'{name}'" in text or f'"{name}"' in text:
            found[name] = body
    return found
