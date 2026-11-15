"""Records the cardbox tutorial: the real app, driven live on this machine, narrated in a cloned voice.

Nothing on screen is mocked. The app is the real `cardbox app`, clicks and typing happen in a real
Chrome window, renders really run, and the terminal shows the real output of commands run while
preparing the recording (with your home folder shown as ~).

usage:
    python tutorial/record.py --voice me [--voice-home ~/Cardbox] [--out tutorial/out]

Needs the voice stack for the narration (`cardbox-video[voice]`, or CARDBOX_VOICE_PYTHON), Google Chrome, and
Playwright's screen-recording encoder: `python -m playwright install ffmpeg`.
Output: tutorial/out/cardbox-tutorial.mp4 (1920x1080).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from cardbox import music
from cardbox.voice.engines import Line, speak

HERE = Path(__file__).resolve().parent
HOME = str(Path.home())

DEMO_SCRIPT = """Your Wi-Fi isn't slow. It's crowded.

# 3 channels
The older band has only three channels that don't overlap.

Follow for more tech, explained simply."""

# (spoken line, pronunciation or None). Each line is paired with one step of the walkthrough below.
NARRATION = [
    ("Hey! In this tutorial, I'll show you how to make a complete video with cardbox, from installing it to posting it. "
     "First, install it with pip.", None),
    ("Then run cardbox doctor. It checks that everything is ready: ffmpeg, the browser it draws with, and voice support.", None),
    ("Now just type cardbox. That's it. The app opens in your browser, and everything runs on your own computer.", None),
    ("Click new video. You get a sample script, ready to edit.", None),
    ("Write what you want to say, one paragraph per beat. The first paragraph is your hook, and the last one is your "
     "ending. You don't need any paid AI for this. Just write.", None),
    ("A line that starts with a hash sets the headline on screen. If it starts with a number, like three channels, "
     "it becomes a big number card.", None),
    ("Now pick the format. Vertical for Reels and Shorts, landscape for YouTube, and square for LinkedIn. "
     "Then pick a theme you like.", None),
    ("Choose the voice, the music, and the caption style, and add your handle. I'll use the computer voice here, "
     "so it renders fast. Your own voice works exactly the same way.", None),
    ("You can add your own images or video clips. Name a file one dot jpg, and it goes behind the first beat.", None),
    ("Click save and preview, to see every frame before you render.", None),
    ("Happy with it? Click make the video. cardbox records the voice, draws every frame, adds captions and music, "
     "and puts it all together.", None),
    ("And here's the video. Download it, and copy the caption. It's ready to post.", None),
    ("To use your own voice, open the voice panel, and read ten short lines, about one minute. cardbox clones your "
     "voice on your computer, and checks every line it speaks, re-recording any word that comes out wrong.", None),
    ("Want full control? Open advanced, and edit the spec directly, with animated scenes and animations timed to "
     "your words.", None),
    ("And if you use an AI assistant like Claude or Cursor, add cardbox as an MCP server. Then just ask for a video, "
     "and it writes the script, finds images, and renders it for you.",
     "And if you use an AI assistant like Claude or Cursor, add cardbox as an M C P server. Then just ask for a video, "
     "and it writes the script, finds images, and renders it for you."),
    ("Prefer the terminal? cardbox make turns a text file into a video, with one command.", None),
    ("That's cardbox. It's free and open source, and the link is in the description. Happy making!", None),
]

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.6L9.6 21z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '-40px', top: '-40px', zIndex: 2147483647, pointerEvents: 'none' });
    document.documentElement.appendChild(c);
    addEventListener('mousemove', (e) => { c.style.left = e.clientX - 4 + 'px'; c.style.top = e.clientY - 3 + 'px'; }, true);
    addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      Object.assign(r.style, { position: 'fixed', left: e.clientX - 20 + 'px', top: e.clientY - 20 + 'px', width: '40px', height: '40px',
        borderRadius: '50%', border: '3px solid #FFE14D', zIndex: 2147483646, pointerEvents: 'none', transition: 'transform .45s ease-out, opacity .45s' });
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.9)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 520);
    }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', add); else add();
})();
"""


def clean(text: str) -> str:
    """Real command output, with this machine's home folder shown as ~."""
    return text.replace(HOME, "~").rstrip()


def run(cmd: list[str], env: dict) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
    return clean(r.stdout + (("\n" + r.stderr) if r.returncode else ""))


class Director:
    """Drives the page and keeps the timeline: when each narration line starts, relative to the video."""

    def __init__(self, page: Page, takes, t0: float):
        self.page, self.takes, self.t0, self.marks = page, takes, t0, []
        self.mouse = (800, 450)

    def now(self) -> float:
        return time.monotonic() - self.t0

    def beat(self, i: int, action) -> None:
        """Starts narration line i, runs its on-screen action, then waits for the line to finish."""
        start = self.now()
        self.marks.append(start)
        action()
        left = self.takes[i].seconds + 0.6 - (self.now() - start)
        if left > 0:
            self.page.wait_for_timeout(left * 1000)

    def move(self, selector: str, dx: float = 0.5, dy: float = 0.5) -> tuple[float, float]:
        target = self.page.locator(selector).first
        target.scroll_into_view_if_needed()
        self.page.wait_for_timeout(250)
        box = target.bounding_box()
        if not box:
            raise RuntimeError(f"not on screen: {selector}")
        x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
        self.page.mouse.move(x, y, steps=28)
        self.mouse = (x, y)
        self.page.wait_for_timeout(180)
        return x, y

    def click(self, selector: str) -> None:
        self.move(selector)
        self.page.mouse.down()
        self.page.wait_for_timeout(70)
        self.page.mouse.up()
        self.page.wait_for_timeout(350)

    def park(self) -> None:
        self.page.mouse.move(*self.mouse)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="the recorded voice that narrates")
    ap.add_argument("--voice-home", default=str(Path.home() / "Cardbox"), help="the workspace that has that voice")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--port", type=int, default=8750)
    a = ap.parse_args()

    out = Path(a.out).resolve()
    home = out / "home"
    shutil.rmtree(home, ignore_errors=True)
    (home / "voices").mkdir(parents=True)
    if a.voice != "none":  # "none": a silent dry run to check the on-screen choreography
        shutil.copytree(Path(a.voice_home).expanduser() / "voices" / a.voice, home / "voices" / a.voice)
    env = {**os.environ, "CARDBOX_HOME": str(home)}
    cardbox = str(Path(sys.executable).with_name("cardbox"))

    # Demo files: an image for "1.jpg" (generated, so there are no rights questions) and the CLI script.
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "mandelbrot=s=1600x900:end_scale=0.4",
                    "-frames:v", "1", str(assets / "1.jpg")], check=True)
    (assets / "wifi.txt").write_text(DEMO_SCRIPT, encoding="utf-8")
    (assets / "mcp.json").write_text('{\n  "mcpServers": {\n    "cardbox": { "command": "cardbox", "args": ["mcp"] }\n  }\n}\n')

    print("capturing real command output…", flush=True)
    doctor = run([cardbox, "doctor"], env)
    make = run([cardbox, "make", str(assets / "wifi.txt"), "--name", "wifi", "--format", "landscape", "--voice", "none",
                "--render"], env).replace(str(assets), "~")
    make = "\n".join(ln for ln in make.splitlines() if not ln.strip().startswith(("beat ", "@progress")))

    print("narrating…", flush=True)
    takes = speak([Line(s, p or s) for s, p in NARRATION], a.voice, out / "voice", log=lambda m: print(m, flush=True))
    weak = [i for i, t in enumerate(takes) if t.score is not None and t.score < 0.97]
    if weak:
        print(f"warning: narration lines {weak} may have a misspoken word", flush=True)

    app = subprocess.Popen([cardbox, "app", "--port", str(a.port), "--no-browser"], env={**env, "PYTHONUNBUFFERED": "1"},
                           stdout=subprocess.PIPE, text=True)
    app_lines = [clean(app.stdout.readline()) for _ in range(2)]
    app_url = f"http://127.0.0.1:{a.port}/"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            # A 1600x900 window recorded at 1920x1080: everything appears 20% larger, readable on a phone.
            ctx = browser.new_context(viewport={"width": 1600, "height": 900}, record_video_dir=str(out / "raw"),
                                      record_video_size={"width": 1920, "height": 1080})
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            t0 = time.monotonic()
            page.goto((HERE / "terminal.html").as_uri())
            page.wait_for_timeout(1200)
            d = Director(page, takes, t0)
            term = lambda js, *args: page.evaluate(js, *args)  # noqa: E731

            d.beat(0, lambda: term("() => term.type('pip install cardbox-video')"))
            d.beat(1, lambda: (term("() => term.prompt()"), term("() => term.type('cardbox doctor')"),
                               term("(t) => term.print(t)", doctor)))
            def open_app():
                term("() => term.prompt()")
                term("() => term.type('cardbox')")
                term("(t) => term.print(t)", "\n".join(app_lines))
                page.wait_for_timeout(2200)
                page.goto(app_url)
                page.wait_for_selector("#script")
                page.mouse.move(800, 500, steps=10)
            d.beat(2, open_app)
            d.beat(3, lambda: d.click("#new"))

            def write():
                d.click("#script")
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(DEMO_SCRIPT, delay=28)
                d.click("#title")
                page.keyboard.type("Why your Wi-Fi is slow", delay=45)
            d.beat(4, write)
            d.beat(5, lambda: (d.move("#script", 0.3, 0.32), page.wait_for_timeout(1500), d.move("#script", 0.2, 0.36)))

            def look():
                for f in ("Vertical", "Landscape", "Square", "Landscape"):
                    d.click(f"#format button:has-text('{f}')")
                    page.wait_for_timeout(500)
                for t in ("neon", "sunset", "midnight"):
                    d.click(f"#theme button[title='{t}']")
                    page.wait_for_timeout(450)
            d.beat(6, look)

            def style():
                d.move("#voice")
                page.select_option("#voice", "system")
                d.move("#music")
                page.select_option("#music", "upbeat")
                d.move("#captions")
                page.select_option("#captions", "box")
                d.click("#handle")
                page.keyboard.type("@inguzdev", delay=60)
            d.beat(7, style)

            def media():
                with page.expect_file_chooser() as fc:
                    d.click("#drop")
                fc.value.set_files(str(assets / "1.jpg"))
                page.wait_for_selector("#media .m")
                d.move("#media .m")
            d.beat(8, media)

            def preview():
                d.click("#preview")
                page.wait_for_function("document.querySelector('#msg').textContent.startsWith('Preview ready')", timeout=180000)
                page.locator("#beats").scroll_into_view_if_needed()
            d.beat(9, preview)

            def render():
                page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                page.wait_for_timeout(500)
                d.click("#render")
            d.beat(10, render)
            page.wait_for_function("document.querySelector('#msg').textContent.startsWith('Done')", timeout=600000)

            def result():
                page.wait_for_timeout(1300)
                page.evaluate("document.getElementById('video').muted = true; document.getElementById('video').play()")
                d.move("#video")
                page.wait_for_timeout(2500)
                d.move("#download")
                page.wait_for_timeout(600)
                d.click("#copy")
            d.beat(11, result)

            def voice():
                page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                page.wait_for_timeout(500)
                d.click("#voicebox button")
                page.wait_for_timeout(2500)
            d.beat(12, voice)

            def yaml_panel():
                d.click("#close")
                d.click("details summary")
                page.locator("#yaml").scroll_into_view_if_needed()
                d.move("#yaml", 0.4, 0.3)
            d.beat(13, yaml_panel)

            def mcp():
                page.goto((HERE / "terminal.html").as_uri())
                page.wait_for_timeout(300)
                page.mouse.move(1450, 820, steps=5)
                term("() => term.type('cat mcp.json')")
                term("(t) => term.print(t)", (assets / "mcp.json").read_text().rstrip())
            d.beat(14, mcp)

            def cli():
                term("() => term.prompt()")
                term("() => term.type('cardbox make wifi.txt --format landscape --render', 40)")
                term("(t) => term.print(t)", make)
            d.beat(15, cli)

            def outro():
                page.goto(app_url)
                page.wait_for_selector("#script")
            d.beat(16, outro)
            page.wait_for_timeout(1500)
            total = d.now()
            video_path = Path(page.video.path())
            ctx.close()
            browser.close()
    finally:
        app.terminate()

    print("mixing…", flush=True)
    bed = music.write(out / "music.wav", music.bed(total, cuts=[], mood="calm"))
    inputs = ["-i", str(video_path), "-i", str(bed)]
    filt = []
    voiced = [(t, m) for t, m in zip(takes, d.marks) if t.wav]
    for i, (take, mark) in enumerate(voiced):
        inputs += ["-i", str(take.wav)]
        ms = int((mark + 0.25) * 1000)
        filt.append(f"[{i + 2}:a]highpass=f=70,loudnorm=I=-16:TP=-1.5,aresample=44100,aformat=channel_layouts=stereo,"
                    f"adelay={ms}|{ms}[v{i}]")
    n = len(voiced)
    if n:
        filt.append("".join(f"[v{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total:.2f}[vo]")
        filt += ["[1:a]volume=0.22[m]", "[vo]asplit[a1][a2]",
                 "[m][a1]sidechaincompress=threshold=0.015:ratio=9:attack=20:release=500[d]",
                 "[d][a2]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.0[a]"]
    else:
        filt.append("[1:a]volume=0.4[a]")
    dest = out / "cardbox-tutorial.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
                    "-r", "30", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.2f}", str(dest)], check=True)
    print(f"done: {dest} ({total:.0f}s)")


if __name__ == "__main__":
    main()
