"""The recording studio: a local web page that walks you through the voice prompts.

The browser records each prompt (MediaRecorder), uploads it here, and gets an instant quality check
back: too quiet, clipping, background noise. Nothing leaves your machine.
"""

from __future__ import annotations

import json
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..localguard import allowed
from ..workspace import TEMPLATES
from .profile import CONSENT, PROMPTS, Profile

_servers: dict[str, tuple[ThreadingHTTPServer, str]] = {}


def _handler(profile: Profile):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the terminal quiet
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

        def _json(self, data: dict, code: int = 200) -> None:
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                page = (TEMPLATES / "studio.html").read_text(encoding="utf-8")
                page = page.replace("__DATA__", json.dumps({"voice": profile.name, "prompts": PROMPTS, "consent": CONSENT}))
                body = page.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/status":
                self._json(profile.status())
            elif path.startswith("/take/") and path.endswith(".wav"):
                f = profile.take_path(int(path[6:8]))
                if not f.exists():
                    return self._json({"error": "no such take"}, 404)
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not path.startswith("/take/"):
                return self._json({"error": "not found"}, 404)
            try:
                i = int(path.split("/")[2])
            except ValueError:
                return self._json({"error": "bad take index"}, 400)
            if i > 0 and not profile.consented:
                return self._json({"error": "record the consent line first"}, 400)
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(data)
                tmp = Path(f.name)
            try:
                q = profile.save_take(i, tmp)
            except Exception as e:  # noqa: BLE001 - report any decode failure to the page
                return self._json({"error": f"couldn't read that recording: {e}"}, 400)
            finally:
                tmp.unlink(missing_ok=True)
            self._json({"ok": q.ok, "issues": q.issues, "seconds": q.seconds, "status": profile.status()})

    return Handler


def start(voice: str, port: int = 8765, open_browser: bool = True) -> str:
    """Starts (or reuses) the studio for a voice in a background thread. Returns its URL."""
    profile = Profile(voice)
    if profile.name in _servers:
        url = _servers[profile.name][1]
    else:
        server = None
        for p in range(port, port + 20):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", p), _handler(profile))
                break
            except OSError:
                continue
        if server is None:
            raise RuntimeError("no free port for the recording studio")
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _servers[profile.name] = (server, url)
    if open_browser:
        webbrowser.open(url)
    return url


def serve_forever(voice: str, port: int = 8765) -> None:
    """For the CLI: start the studio and keep running until Ctrl+C."""
    url = start(voice, port)
    print(f"Recording studio for voice '{Profile(voice).name}': {url}\nPress Ctrl+C when you're done.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print()
