"""A headless browser for drawing: cards are HTML, scenes are canvas animations.

Uses Playwright's Chromium, or an installed Google Chrome when the bundled browser isn't there.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, Error, Page, sync_playwright

W, H = 1080, 1920
ARGS = ["--allow-file-access-from-files", "--disable-web-security", "--font-render-hinting=none"]


def _launch(pw) -> Browser:
    channel = os.environ.get("CARDBOX_BROWSER_CHANNEL")
    attempts = [{"channel": channel}] if channel else [{}, {"channel": "chrome"}]
    last: Exception | None = None
    for opts in attempts:
        try:
            return pw.chromium.launch(headless=True, args=ARGS, **opts)
        except Error as e:
            last = e
    raise RuntimeError(
        "No browser available for rendering. Run `python -m playwright install chromium` "
        f"(or install Google Chrome). Details: {last}"
    )


@contextmanager
def page(w: int = W, h: int = H) -> Iterator[Page]:
    """A w×h page (default 1080x1920), closed with its browser on exit."""
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            p = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            yield p
        finally:
            browser.close()


def load_html(p: Page, html: str) -> None:
    """Loads HTML from a temp file (not set_content) so file:// fonts and images are allowed."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = Path(f.name)
    try:
        p.goto(tmp.as_uri(), wait_until="load")
        p.evaluate("document.fonts.ready")
    finally:
        tmp.unlink(missing_ok=True)


def shot(p: Page, html: str, out: Path, transparent: bool = False) -> None:
    load_html(p, html)
    p.screenshot(path=str(out), omit_background=transparent)
