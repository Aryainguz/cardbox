"""Turns spoken lines into audio, with word timings.

Voices:
  <profile>  your cloned voice (Chatterbox), every take checked by Whisper and retried if it's off
  system     the operating system's voice (macOS `say`, Linux `espeak-ng`), no extra installs
  none       silent: durations are estimated, handy for fast previews of the visuals

Takes are cached by their text and settings, so editing one line of a reel re-speaks only that line.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..captions import estimate_seconds, spread, words
from .align import map_words
from .profile import Profile

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # the folder that contains the `cardbox` package


@dataclass
class Line:
    say: str  # the caption text
    speak: str  # what the voice reads (pronunciation override, or the same)


@dataclass
class Take:
    wav: Path | None
    seconds: float
    word_times: list[tuple[float, float]]  # per caption word, from the line's start
    score: float | None = None
    heard: str = ""


def voice_python() -> str:
    """The interpreter that has the voice stack (PyTorch, Chatterbox, Whisper)."""
    return os.environ.get("CARDBOX_VOICE_PYTHON") or sys.executable


def has_voice_stack(modules: tuple[str, ...] = ("chatterbox", "whisper")) -> dict[str, bool]:
    code = "import importlib.util,json,sys;print(json.dumps({m: importlib.util.find_spec(m) is not None for m in sys.argv[1:]}))"
    try:
        r = subprocess.run([voice_python(), "-c", code, *modules], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return {m: False for m in modules}


def duration(wav: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _key(*parts: object) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:16]


def _system_say(text: str, out: Path) -> None:
    if platform.system() == "Darwin" and shutil.which("say"):
        aiff = out.with_suffix(".aiff")
        subprocess.run(["say", "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(aiff), "-ac", "1", "-ar", "24000", str(out)], check=True)
        aiff.unlink(missing_ok=True)
    elif shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", "-s", "165", "-w", str(out), text], check=True)
    else:
        raise RuntimeError("no system voice found: install espeak-ng, record your own voice, or use voice: none")


def _worker(spec: dict, log=print) -> list[dict]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        path = f.name
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(PACKAGE_ROOT), os.environ.get("PYTHONPATH", "")])}
    try:
        proc = subprocess.Popen([voice_python(), "-m", "cardbox.voice.worker", path], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        out, err = proc.communicate()
    finally:
        os.unlink(path)
    if proc.returncode:
        raise RuntimeError(f"voice worker failed:\n{err[-2000:]}")
    for line in err.splitlines():
        if line.startswith("{"):
            log("  voice " + line)
    report = [ln for ln in out.splitlines() if ln.startswith("REPORT ")]
    return json.loads(report[-1][7:]) if report else []


def system_voice_available() -> bool:
    return (platform.system() == "Darwin" and bool(shutil.which("say"))) or bool(shutil.which("espeak-ng"))


def resolve_voice(voice: str) -> str:
    """'auto' → a recorded voice that's ready (preferring 'default', then 'me') if voice cloning
    is installed, else the computer's voice, else silence. So a video always renders without errors."""
    if voice != "auto":
        return voice
    stack = has_voice_stack()
    if stack.get("chatterbox"):
        ready = [n for n in Profile.all() if Profile(n).status()["ready"]]
        for name in ("default", "me", *ready):
            if name in ready:
                return name
    return "system" if system_voice_available() else "none"


def speak(lines: list[Line], voice: str, cache: Path, settings: dict | None = None, log=print) -> list[Take]:
    """Speaks every line in `voice`, reusing cached takes. Returns one Take per line."""
    settings = settings or {}
    cache.mkdir(parents=True, exist_ok=True)
    voice = resolve_voice(voice)
    if voice == "none":
        return [Take(None, estimate_seconds(ln.say), spread(ln.say, estimate_seconds(ln.say))) for ln in lines]

    stack = has_voice_stack()
    files = [cache / f"{_key(voice, ln.speak, settings)}.wav" for ln in lines]
    todo = [i for i, f in enumerate(files) if not (f.exists() and Path(str(f) + ".heard.json").exists())]
    if todo:
        if voice == "system":
            for i in todo:
                _system_say(lines[i].speak, files[i])
            jobs = [{"text": lines[i].speak, "expect": lines[i].say, "out": str(files[i])} for i in todo]
            if stack.get("whisper"):
                _worker({"engine": "file", "jobs": jobs, "retries": 1}, log)
            else:
                for i in todo:
                    Path(str(files[i]) + ".heard.json").write_text(json.dumps({"text": "", "words": [], "score": None}))
        else:
            if not stack.get("chatterbox"):
                is_pipx = "pipx" in sys.executable or "pipx" in os.environ.get("VIRTUAL_ENV", "")
                cmd = "pipx inject cardbox-video 'cardbox-video[voice]'" if is_pipx else "pip install 'cardbox-video[voice]'"
                raise RuntimeError(f"voice cloning needs the voice extras: run `{cmd}` "
                                   f"(or point CARDBOX_VOICE_PYTHON at an environment that has them)")
            ref = Profile(voice).reference()
            jobs = [{"text": lines[i].speak, "expect": lines[i].say, "out": str(files[i]), "seed": 7 + i} for i in todo]
            log(f"  cloning {len(jobs)} line(s) in voice '{voice}' (each take is checked and retried if words are off)")
            _worker({"engine": "chatterbox", "reference": str(ref), "jobs": jobs, **settings}, log)

    takes = []
    for ln, f in zip(lines, files):
        heard = json.loads(Path(str(f) + ".heard.json").read_text())
        secs = duration(f)
        cap = words(ln.say)
        times = map_words(cap, [tuple(w) for w in heard["words"]], secs) if heard["words"] else spread(ln.say, secs)
        score = heard.get("score")
        if heard.get("errors"):  # any wrong word marks the line as needing a look, whatever its score
            score = min(score or 1.0, 0.96)
        takes.append(Take(f, secs, times, score, heard.get("text", "")))
    return takes
