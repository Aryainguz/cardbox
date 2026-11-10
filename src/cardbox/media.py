"""Finds images on the open web that you're allowed to use, and keeps their credits.

Sources: Openverse (800M+ openly licensed images) and Wikimedia Commons. Only licenses that allow
reuse and modification, commercially, are returned: CC0, public domain, CC BY and CC BY-SA. Every
download is recorded in the reel's media/credits.json, and the attribution lands in caption.txt.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

UA = {"User-Agent": "cardbox/0.1 (+https://github.com/aryainguz/cardbox)"}
OPENVERSE = "https://api.openverse.org/v1/images/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
COMMONS_OK = re.compile(r"^(public domain|pd|cc0|cc by(-sa)?( [0-9.]+)?)$", re.I)


@dataclass
class Image:
    id: str
    title: str
    url: str
    thumbnail: str
    width: int | None
    height: int | None
    license: str
    author: str
    page: str
    provider: str

    def credit(self) -> str:
        who = f" by {self.author}" if self.author else ""
        return f"“{self.title}”{who} ({self.license}), via {self.provider}"


def _get(url: str) -> dict:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _openverse_item(r: dict) -> Image:
    lic = r.get("license", "")
    name = "Public domain" if lic in ("pdm", "cc0") else f"CC {lic.upper()} {r.get('license_version') or ''}".strip()
    return Image(id=f"openverse:{r['id']}", title=(r.get("title") or "Untitled")[:120], url=r["url"],
                 thumbnail=r.get("thumbnail") or r["url"], width=r.get("width"), height=r.get("height"), license=name,
                 author=r.get("creator") or "", page=r.get("foreign_landing_url") or "", provider="Openverse")


def search_openverse(query: str, n: int = 8) -> list[Image]:
    q = urllib.parse.urlencode({"q": query, "license": "by,by-sa,cc0,pdm", "page_size": n, "mature": "false"})
    return [_openverse_item(r) for r in _get(f"{OPENVERSE}?{q}").get("results", [])]


def _commons_info(titles: list[str]) -> list[Image]:
    q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles), "prop": "imageinfo", "format": "json",
                                "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1800})
    out = []
    for p in _get(f"{COMMONS}?{q}").get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not COMMONS_OK.match(lic.strip()) or ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        author = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
        out.append(Image(id=f"commons:{p['title']}", title=p["title"].removeprefix("File:").rsplit(".", 1)[0],
                         url=ii.get("thumburl") or ii["url"], thumbnail=ii.get("thumburl") or ii["url"],
                         width=ii.get("width"), height=ii.get("height"), license=lic, author=author[:80],
                         page=ii.get("descriptionurl", ""), provider="Wikimedia Commons"))
    return out


def search_commons(query: str, n: int = 8) -> list[Image]:
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srnamespace": 6, "format": "json",
                                "srsearch": f"{query} filetype:bitmap", "srlimit": n})
    titles = [h["title"] for h in _get(f"{COMMONS}?{q}").get("query", {}).get("search", [])]
    return _commons_info(titles) if titles else []


def search(query: str, n: int = 8, sources: tuple[str, ...] = ("openverse", "commons")) -> list[Image]:
    """Openly licensed images for `query`, best first, interleaving sources."""
    found: list[list[Image]] = []
    for s in sources:
        try:
            found.append(search_openverse(query, n) if s == "openverse" else search_commons(query, n))
        except Exception:  # noqa: BLE001 - one source being down shouldn't stop the other
            found.append([])
    out, seen = [], set()
    for row in zip(*[f + [None] * (n - len(f)) for f in found]):
        for img in row:
            if img and img.url not in seen:
                seen.add(img.url)
                out.append(img)
    return out[:n]


def lookup(image_id: str) -> Image:
    provider, _, key = image_id.partition(":")
    if provider == "openverse":
        return _openverse_item(_get(f"{OPENVERSE}{key}/"))
    if provider == "commons":
        found = _commons_info([key])
        if not found:
            raise ValueError(f"{image_id} isn't available under a reusable license")
        return found[0]
    raise ValueError(f"unknown image id {image_id!r} (expected openverse:… or commons:…)")


def fetch(image_id: str, reel_dir: Path, name: str) -> tuple[Path, Image]:
    """Downloads an image into the reel's media/ folder and records its credit."""
    img = lookup(image_id)
    media = reel_dir / "media"
    media.mkdir(parents=True, exist_ok=True)
    ext = ".png" if img.url.lower().endswith(".png") else ".jpg"
    dest = media / f"{re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-') or 'image'}{ext}"
    with urllib.request.urlopen(urllib.request.Request(img.url, headers=UA), timeout=60) as r:
        dest.write_bytes(r.read())
    credits_path = media / "credits.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    credits[dest.name] = asdict(img)
    credits_path.write_text(json.dumps(credits, indent=2, ensure_ascii=False))
    return dest, img


def credits_for(reel_dir: Path, used: set[str]) -> list[str]:
    """Attribution lines for the downloaded images this reel actually uses."""
    path = reel_dir / "media" / "credits.json"
    if not path.exists():
        return []
    credits = json.loads(path.read_text())
    out = []
    for file, c in credits.items():
        if any(Path(u).name == file for u in used):
            out.append(Image(**c).credit())
    return out
