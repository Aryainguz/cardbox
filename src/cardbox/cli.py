"""cardbox command line.

    cardbox                               open the app in your browser (the easiest way)

    cardbox make script.txt --render      plain text in (one paragraph per beat), video out
    cardbox new my-reel                 start a YAML spec from the template (full control)
    cardbox render my-reel              render it (or a path to a spec file)
    cardbox preview my-reel 2           a still of beat 2
    cardbox voice record [name]         record your voice in the browser studio
    cardbox voice status [name]
    cardbox voice test "Hello there" [--voice name]
    cardbox images "golden gate bridge" search openly licensed images
    cardbox images get <id> --reel my-reel --name bridge
    cardbox scenes                      the scene library
    cardbox doctor                      check ffmpeg, browser and voice setup
    cardbox mcp                         run the MCP server (stdio)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__

TEMPLATE = Path(__file__).parent / "templates" / "reel.yaml"


def _new(a: argparse.Namespace) -> None:
    from .workspace import reel_dir

    d = reel_dir(a.name)
    dest = d / "reel.yaml"
    if dest.exists() and not a.force:
        sys.exit(f"{dest} already exists (use --force to overwrite)")
    shutil.copy(TEMPLATE, dest)
    print(f"Created {dest}\nEdit it, then: cardbox render {a.name}")


def _make(a: argparse.Namespace) -> None:
    from . import spec
    from .script import from_text
    from .workspace import reel_dir, slug

    src = Path(a.script)
    text = sys.stdin.read() if a.script == "-" else src.read_text(encoding="utf-8") if src.exists() else a.script
    name = a.name or (src.stem if src.exists() else "video")
    opts = {k: v for k, v in {"format": a.format, "theme": a.theme, "voice": a.voice, "handle": a.handle,
                              "music": a.music, "captions": a.captions}.items() if v}
    d = reel_dir(name)
    if src.exists() and (src.parent / "media").is_dir():  # media next to the script comes along
        shutil.copytree(src.parent / "media", d / "media", dirs_exist_ok=True)
    reel = from_text(text, media_dir=d / "media", **opts)
    dest = d / "reel.yaml"
    dest.write_text(spec.dump(reel), encoding="utf-8")
    print(f"{len(reel.beats)} beats → {dest}")
    if a.render:
        from .render import render

        r = render(slug(name))
        print(f"\n{r.video}  ({r.seconds:.1f}s)\ncaption: {r.caption}")
    else:
        print(f"Preview: cardbox preview {slug(name)} 0    Render: cardbox render {slug(name)}")


def _render(a: argparse.Namespace) -> None:
    from .render import render

    r = render(a.reel, Path(a.out) if a.out else None)
    print(f"\n{r.video}  ({r.seconds:.1f}s)\ncaption: {r.caption}")


def _preview(a: argparse.Namespace) -> None:
    from .render import preview

    print(preview(a.reel, a.beat, a.at))


def _voice(a: argparse.Namespace) -> None:
    from .voice.profile import Profile

    if a.action == "record":
        from .voice.studio import serve_forever

        serve_forever(a.name)
    elif a.action == "status":
        print(json.dumps(Profile(a.name).status(), indent=2))
    elif a.action == "recheck":
        st = Profile(a.name).recheck()
        print(f"{st['good']}/{st['recorded']} takes pass the quality check · ready: {st['ready']}")
    elif a.action == "list":
        print("\n".join(Profile.all()) or "no voices recorded yet: cardbox voice record")
    elif a.action == "test":
        from .voice.engines import Line, speak
        from .workspace import home, slug

        take = speak([Line(a.name, a.name)], a.voice, home() / "voices" / slug(a.voice) / "tests")[0]
        print(f"{take.wav}\nheard: {take.heard!r}  match: {take.score}")


def _images(a: argparse.Namespace) -> None:
    from . import media

    if a.query and a.query[0] == "get":
        from .workspace import reel_dir

        if len(a.query) < 2 or not a.reel:
            sys.exit("usage: cardbox images get <id> --reel NAME [--name NAME]")
        path, img = media.fetch(a.query[1], reel_dir(a.reel), a.name or "image")
        print(f"{path}\n{img.credit()}")
        return
    for i in media.search(" ".join(a.query), a.limit):
        print(f"{i.id}\n    {i.title[:70]}  ·  {i.license}  ·  {i.author[:40]}  ·  {i.width}x{i.height}")


def _scenes(_: argparse.Namespace) -> None:
    from .scenes import CATALOG

    for k, v in CATALOG.items():
        print(f"{k:10} {v}\n")


def _doctor(_: argparse.Namespace) -> None:
    from .voice.engines import has_voice_stack, voice_python

    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        ok &= bool(found)
        print(f"{'✓' if found else '✗'} {tool}: {found or 'missing (brew install ffmpeg / apt install ffmpeg)'}")
    try:
        from .browser import page

        with page():
            pass
        print("✓ browser: ready")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"✗ browser: {e}")
    stack = has_voice_stack()
    print(f"{'✓' if all(stack.values()) else '·'} voice cloning ({voice_python()}): "
          + ", ".join(f"{k} {'ok' if v else 'missing'}" for k, v in stack.items()))
    if not all(stack.values()):
        is_pipx = "pipx" in sys.executable or "pipx" in os.environ.get("VIRTUAL_ENV", "")
        hint = "pipx install --force cardbox-video" if is_pipx else "pip install --force-reinstall cardbox-video"
        print(f"    models missing: run `{hint}` (or set CARDBOX_VOICE_PYTHON)")
    say = shutil.which("say") or shutil.which("espeak-ng")
    print(f"{'✓' if say else '·'} system voice: {say or 'none (voice: system unavailable)'}")
    sys.exit(0 if ok else 1)


def _app(a: argparse.Namespace) -> None:
    from .app import serve

    serve(port=getattr(a, "port", 8740), open_browser=not getattr(a, "no_browser", False))


def _mcp(_: argparse.Namespace) -> None:
    from .mcp_server import main

    main()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="cardbox", description="Plain text in, finished video out. Run with no arguments to open the app.")
    ap.add_argument("--version", action="version", version=f"cardbox {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("app", help="open the cardbox app in your browser (also what plain `cardbox` does)")
    p.add_argument("--port", type=int, default=8740)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=_app)

    p = sub.add_parser("make", help="plain-text script (a file, '-' for stdin, or the text itself) → video")
    p.add_argument("script")
    p.add_argument("--name")
    p.add_argument("--format", help="vertical | landscape | square")
    p.add_argument("--theme")
    p.add_argument("--voice", help="your voice name, system, or none")
    p.add_argument("--handle")
    p.add_argument("--music")
    p.add_argument("--captions")
    p.add_argument("--render", action="store_true", help="render right away")
    p.set_defaults(fn=_make)

    p = sub.add_parser("new", help="start a YAML spec from the template (full control)")
    p.add_argument("name")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=_new)

    p = sub.add_parser("render", help="render a video (its name, or a spec file) to MP4")
    p.add_argument("reel", help="video name or path to a spec file")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=_render)

    p = sub.add_parser("preview", help="a PNG still of one beat")
    p.add_argument("reel")
    p.add_argument("beat", type=int)
    p.add_argument("--at", type=float, default=0.7)
    p.set_defaults(fn=_preview)

    p = sub.add_parser("voice", help="record, check and test voices")
    p.add_argument("action", choices=["record", "status", "list", "test", "recheck"])
    p.add_argument("name", nargs="?", default="default", help="voice name (for test: the text to speak)")
    p.add_argument("--voice", default="default", help="voice to test with")
    p.set_defaults(fn=_voice)

    p = sub.add_parser("images", help="search or download openly licensed images")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--reel")
    p.add_argument("--name")
    p.set_defaults(fn=_images)

    sub.add_parser("scenes", help="list the scene library").set_defaults(fn=_scenes)
    sub.add_parser("doctor", help="check your setup").set_defaults(fn=_doctor)
    sub.add_parser("mcp", help="run the MCP server over stdio").set_defaults(fn=_mcp)

    a = ap.parse_args(argv)
    if a.cmd is None:  # plain `cardbox`: the app
        a.fn = _app
    try:
        a.fn(a)
    except (FileNotFoundError, RuntimeError, ValueError, IndexError) as e:
        sys.exit(f"error: {e}")
    except subprocess.CalledProcessError as e:
        sys.exit(f"error: {' '.join(map(str, e.cmd[:3]))}… failed")


if __name__ == "__main__":
    main()
