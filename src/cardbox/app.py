"""The local app: run `cardbox` and it opens in your browser.

Write a script, pick a format and style, drop in images or clips, record your voice, preview frames,
render with a progress bar, then watch, download and copy the caption. Everything is stored in the
normal workspace (~/Cardbox), so the CLI, the MCP server and the app all see the same videos. The app
writes the YAML spec for you; an Advanced panel lets you edit it directly.

Bound to 127.0.0.1 only: nothing is reachable from other machines.
"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml
from pydantic import ValidationError

from . import formats, spec, themes
from .localguard import allowed
from .script import IMAGE_EXT, VIDEO_EXT, from_text
from .voice.profile import Profile
from .workspace import TEMPLATES, home, reel_dir, slug

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
OPTION_KEYS = ("format", "theme", "voice", "music", "captions", "handle", "accent", "font")


def options() -> dict:
    """Everything the editor offers, so the page never hard-codes a list."""
    return {
        "formats": [{"name": f.name, "size": f"{f.w}×{f.h}", "use": f.use} for f in formats.FORMATS.values()],
        "themes": [{"name": n, "bg": t["bg"], "accent": t["accent"], "accent2": t["accent2"]} for n, t in themes.THEMES.items()],
        "music": ["calm", "upbeat", "tense", "none"],
        "captions": ["highlight", "box", "minimal", "none"],
        "fonts": ["sans", "mono"],
    }


def voices() -> list[dict]:
    out = []
    for name in Profile.all():
        st = Profile(name).status()
        out.append({"name": name, "ready": st["ready"], "recorded": st["good"], "total": st["total_prompts"]})
    return out


def _video_file(d: Path) -> Path:
    return d / f"{d.name}.mp4"


def reels() -> list[dict]:
    root = home() / "reels"
    out = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []:
        if (d / "reel.yaml").exists():
            try:
                title = yaml.safe_load((d / "reel.yaml").read_text()).get("title", d.name)
            except Exception:  # noqa: BLE001 - a broken spec still shows up in the list
                title = d.name
            out.append({"name": d.name, "title": title, "rendered": _video_file(d).exists()})
    return out


def media_list(d: Path) -> list[dict]:
    m = d / "media"
    if not m.is_dir():
        return []
    files = []
    for f in sorted(m.iterdir()):
        ext = f.suffix.lower()
        if ext in IMAGE_EXT | VIDEO_EXT:
            files.append({"name": f.name, "kind": "video" if ext in VIDEO_EXT else "image", "size": f.stat().st_size})
    return files


def reel_info(name: str) -> dict:
    d = reel_dir(name)
    info: dict = {"name": d.name, "script": "", "yaml": "", "options": {}, "title": "", "media": media_list(d),
                  "video": None, "caption": "", "beats": [], "error": None}
    if (d / "script.txt").exists():
        info["script"] = (d / "script.txt").read_text(encoding="utf-8")
    if (d / "reel.yaml").exists():
        info["yaml"] = (d / "reel.yaml").read_text(encoding="utf-8")
        try:
            r = spec.parse(info["yaml"])
            info["title"] = r.title
            info["options"] = {k: getattr(r, k) for k in OPTION_KEYS}
            info["beats"] = [{"kind": b.kind, "text": getattr(b, "text", "") or getattr(b, "value", "") or getattr(b, "head", "")}
                             for b in r.beats]
        except (ValidationError, ValueError) as e:
            info["error"] = str(e)
    if _video_file(d).exists():
        info["video"] = f"/files/{d.name}/{d.name}.mp4?v={int(_video_file(d).stat().st_mtime)}"
        cap = d / "caption.txt"
        info["caption"] = cap.read_text(encoding="utf-8") if cap.exists() else ""
    with LOCK:
        info["job"] = JOBS.get(d.name)
    return info


def save(name: str, body: dict) -> dict:
    """Plain-text script + options → script.txt and reel.yaml."""
    d = reel_dir(name)
    script = body.get("script", "")
    opts = {k: v for k, v in (body.get("options") or {}).items() if k in OPTION_KEYS and v not in (None, "")}
    reel = from_text(script, title=body.get("title", ""), media_dir=d / "media", **opts)
    (d / "script.txt").write_text(script, encoding="utf-8")
    (d / "reel.yaml").write_text(spec.dump(reel), encoding="utf-8")
    return reel_info(name)


def save_yaml(name: str, text: str) -> dict:
    spec.parse(text)  # validate before writing
    (reel_dir(name) / "reel.yaml").write_text(text, encoding="utf-8")
    return reel_info(name)


def start_render(name: str) -> dict:
    from .render import render

    d = reel_dir(name)
    with LOCK:
        if JOBS.get(d.name, {}).get("state") == "running":
            return JOBS[d.name]
        job = {"state": "running", "stage": "starting", "done": 0, "total": 0, "error": None, "started": time.time()}
        JOBS[d.name] = job

    def on_progress(stage, done, total, extra):
        with LOCK:
            job.update(stage=stage, done=done, total=total, elapsed=round(time.time() - job["started"]))

    def run():
        try:
            r = render(d / "reel.yaml", on_progress=on_progress)
            with LOCK:
                job.update(state="done", stage="done", seconds=round(r.seconds, 1), elapsed=round(time.time() - job["started"]))
        except Exception as e:  # noqa: BLE001 - shown to the user in the app
            traceback.print_exc()
            with LOCK:
                job.update(state="error", error=str(e).strip().splitlines()[-1][:400] if str(e).strip() else repr(e))

    threading.Thread(target=run, daemon=True).start()
    return job


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def handle_one_request(self) -> None:
        # Every request goes through the local guard first (see localguard.py).
        self.raw_requestline = self.rfile.readline(65537)
        if not self.raw_requestline:
            self.close_connection = True
            return
        if not self.parse_request():
            return
        if not allowed(self.command, self.headers):
            body = b'{"error": "forbidden: cardbox only accepts requests from this computer"}'
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        method = getattr(self, 'do_' + self.command, None)
        if method is None:
            self.send_error(501, 'Unsupported method')
            return
        method()
        self.wfile.flush()

    # ---- responses ----
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _error(self, msg: str, code: int = 400) -> None:
        self._json({"error": msg}, code)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _file(self, path: Path) -> None:
        """Serves a file, with Range support so the video player can seek."""
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng:
            start = int(rng.group(1) or 0)
            end = min(int(rng.group(2) or size - 1), size - 1)
            with path.open("rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
            self._send(206, chunk, ctype, {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
        else:
            self._send(200, path.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

    # ---- routes ----
    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        try:
            if not parts:
                page = (TEMPLATES / "app.html").read_text(encoding="utf-8")
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if parts == ["api", "state"]:
                from .voice.engines import has_voice_stack

                stack = has_voice_stack()
                return self._json({"voices": voices(), "reels": reels(), "options": options(),
                                   "cloning": bool(stack.get("chatterbox")), "home": str(home())})
            if parts[:2] == ["api", "reels"] and len(parts) == 3:
                return self._json(reel_info(parts[2]))
            if parts[:2] == ["api", "reels"] and len(parts) == 5 and parts[3] == "preview":
                from .render import preview

                at = float(parse_qs(url.query).get("at", ["0.9"])[0])
                return self._file(preview(parts[2], int(parts[4]), at))
            if parts[:2] == ["api", "voices"] and len(parts) == 3:
                return self._json(Profile(parts[2]).status())
            if parts[0] == "files" and len(parts) >= 3:
                d = reel_dir(parts[1]).resolve()
                f = (d / "/".join(parts[2:])).resolve()
                if d not in f.parents or not f.is_file():
                    return self._error("not found", 404)
                return self._file(f)
            if parts[0] == "assets" and len(parts) == 2:
                f = (Path(__file__).parent / "assets" / "brand" / parts[1]).resolve()
                if f.is_file():
                    return self._file(f)
            self._error("not found", 404)
        except (ValidationError, ValueError, FileNotFoundError, IndexError, RuntimeError) as e:
            self._error(str(e))

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        try:
            if parts[:2] == ["api", "reels"] and len(parts) == 3:
                return self._json(save(parts[2], json.loads(self._body() or b"{}")))
            if parts[:2] == ["api", "reels"] and len(parts) == 4 and parts[3] == "yaml":
                return self._json(save_yaml(parts[2], self._body().decode("utf-8")))
            if parts[:2] == ["api", "reels"] and len(parts) == 4 and parts[3] == "render":
                return self._json(start_render(parts[2]))
            if parts[:2] == ["api", "reels"] and len(parts) == 4 and parts[3] == "media":
                raw = parse_qs(url.query).get("file", ["upload"])[0]
                stem, ext = Path(raw).stem, Path(raw).suffix.lower()
                if ext not in IMAGE_EXT | VIDEO_EXT:
                    return self._error("only images (jpg, png, webp) and videos (mp4, mov, webm) can be added")
                safe = (re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "file") + ext
                m = reel_dir(parts[2]) / "media"
                m.mkdir(exist_ok=True)
                (m / safe).write_bytes(self._body())
                return self._json({"name": safe, "media": media_list(reel_dir(parts[2]))})
            if parts[:2] == ["api", "voices"] and len(parts) == 4 and parts[3] == "studio":
                from .voice.studio import start

                return self._json({"url": start(parts[2], open_browser=False)})
            self._error("not found", 404)
        except ValidationError as e:
            self._error("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
        except (ValueError, FileNotFoundError, yaml.YAMLError, json.JSONDecodeError) as e:
            self._error(str(e))

    def do_DELETE(self) -> None:  # noqa: N802
        parts = [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]
        if parts[:2] == ["api", "reels"] and len(parts) == 5 and parts[3] == "media":
            m = (reel_dir(parts[2]) / "media").resolve()
            f = (m / parts[4]).resolve()
            if f.parent == m and f.is_file():
                f.unlink()
            return self._json({"media": media_list(reel_dir(parts[2]))})
        if parts[:2] == ["api", "reels"] and len(parts) == 3:
            d = reel_dir(parts[2])
            shutil.rmtree(d, ignore_errors=True)
            return self._json({"deleted": d.name})
        self._error("not found", 404)


def serve(port: int = 8740, open_browser: bool = True) -> None:
    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError("no free port for the cardbox app")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    # flush: when stdout is a pipe (Docker logs, process managers), unflushed output would never appear.
    print(f"cardbox is running at {url}\nYour videos are in {home()}. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


__all__ = ["serve", "slug"]
