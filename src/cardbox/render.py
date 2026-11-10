"""Renders a spec into a finished video (vertical 1080x1920, landscape 1920x1080 or square 1080x1080).

    speak every line (cached) → card + caption images → animated scenes (timed to the words)
    → one clip per beat (build steps, word-by-word captions, progress bar) → concat
    → music bed with a hit on every cut, ducked under the voice → <name>.mp4 + caption.txt
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import cards, formats, music, scenes, themes
from .browser import page
from .captions import chunks, schedule
from .captions import words as caption_words
from .media import credits_for
from .spec import Background, Beat, Reel, SceneBeat, load
from .voice.engines import Line, Take, speak
from .workspace import resolve_reel

FPS = 30
LEAD, PAD = 0.15, 0.4  # silence before each line, breathing room after it
VOICE_CHAIN = "highpass=f=70,loudnorm=I=-16:TP=-1.5,aresample=44100"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def progress(stage: str, done: int = 0, total: int = 0, **extra: object) -> None:
    """Machine-readable progress on stderr (one JSON object per line, prefixed `@progress `), so a job
    runner such as the Go server can stream it to clients. Turned on by CARDBOX_PROGRESS=1."""
    if os.environ.get("CARDBOX_PROGRESS") == "1":
        print("@progress " + json.dumps({"stage": stage, "done": done, "total": total, **extra}), file=sys.stderr, flush=True)


def style(reel: Reel) -> dict:
    return {"theme": reel.theme, "accent": reel.accent, "font": reel.font, "format": reel.format}


def ff(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-1500:]}")


@dataclass
class Result:
    video: Path
    caption: Path
    seconds: float
    voice_scores: list[float | None]


def _background(b: Beat) -> tuple[str, dict] | None:
    """(scene, params) drawn behind a beat, if any."""
    if isinstance(b, SceneBeat):
        return b.scene, b.params
    bg: Background | None = getattr(b, "background", None)
    if bg is None:
        return None
    if bg.scene:
        return bg.scene, bg.params
    if bg.image:
        return "photo", {"image": bg.image, "full": True, **bg.params}
    return None


def _images_used(reel: Reel) -> set[str]:
    used: set[str] = set()

    def walk(v: object) -> None:
        if isinstance(v, dict):
            for k, val in v.items():
                if k == "image" and isinstance(val, str):
                    used.add(val)
                else:
                    walk(val)
        elif isinstance(v, list):
            for i in v:
                walk(i)

    walk(reel.model_dump())
    return used


def caption_text(reel: Reel, base: Path) -> str:
    parts = [reel.caption.strip()] if reel.caption.strip() else [reel.title]
    credits = credits_for(base, _images_used(reel))
    if credits:
        parts.append("Images: " + "; ".join(credits) + ".")
    if reel.hashtags:
        parts.append(" ".join(h if h.startswith("#") else f"#{h}" for h in reel.hashtags))
    return "\n\n".join(parts) + "\n"


def _clip(k: int, dur: float, take: Take, states: list[Path], caps: list[list[Path]], scene_mp4: Path | None,
          offset: float, total: float, build: Path, reel: Reel, out: Path) -> None:
    """One beat: background, card build steps, captions word by word, progress bar."""
    b = reel.beats[k]
    reveal = [0.0] + [LEAD + take.seconds * i / len(states) for i in range(1, len(states))]
    lst = build / f"{k:02d}_states.txt"
    with lst.open("w") as f:
        for i, s in enumerate(states):
            end = reveal[i + 1] if i + 1 < len(states) else dur
            f.write(f"file '{s}'\nduration {max(0.04, end - reveal[i]):.3f}\n")
        f.write(f"file '{states[-1]}'\n")
    groups = chunks(b.say)
    cap_times = schedule(groups, take.word_times, lead=LEAD) if caps else []
    fmt = formats.get(reel.format)
    accent = themes.get(reel.theme, reel.accent)["accent"].lstrip("#")
    bar = build / f"bar_{fmt.w}_{accent}.png"
    if not bar.exists():
        ff("-f", "lavfi", "-i", f"color=c=0x{accent}:s={fmt.w}x8", "-frames:v", "1", str(bar))
    inputs = ["-f", "concat", "-safe", "0", "-i", str(lst), "-loop", "1", "-t", f"{dur:.3f}", "-i", str(bar)]
    for g, w, _, _ in cap_times:
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(caps[g][w])]
    if scene_mp4:
        bi = len(cap_times) + 2
        inputs += ["-i", str(scene_mp4)]
        filt = [f"[{bi}:v]fps={FPS},format=rgba[sc]", f"[0:v]fps={FPS},format=rgba[cd]",
                "[sc][cd]overlay=0:0:format=rgb,fade=in:st=0:d=0.2[c0]"]
    else:
        filt = [f"[0:v]fps={FPS},format=rgba,fade=in:st=0:d=0.2[c0]"]
    filt.append(f"[1:v]format=rgba[b];[c0][b]overlay=x='-{fmt.w}+{fmt.w}*({offset:.3f}+t)/{total:.3f}':y=0:eval=frame:format=rgb[c1]")
    for j, (_, _, a, e) in enumerate(cap_times):
        filt.append(f"[{j + 2}:v]format=rgba[p{j}];[c{j + 1}][p{j}]overlay=0:0:enable='between(t,{a:.3f},{e:.3f})':format=rgb[c{j + 2}]")
    filt.append(f"[c{len(cap_times) + 1}]format=yuv420p[v]")
    ff(*inputs, "-filter_complex", ";".join(filt), "-map", "[v]", "-r", str(FPS), "-c:v", "libx264",
       "-preset", "medium", "-crf", "17", "-t", f"{dur:.3f}", str(out))


def _mix(reel: Reel, takes: list[Take], starts: list[float], total: float, video: Path, build: Path, out: Path) -> None:
    voiced = [(s + LEAD, t.wav) for s, t in zip(starts, takes) if t.wav]
    inputs = ["-i", str(video)]
    filt: list[str] = []
    mood = reel.music_mood
    if mood != "none":
        bed = music.write(build / f"music_{mood}.wav", music.bed(total, cuts=starts[1:], mood=mood))
        inputs += ["-i", str(bed)]
    for _, wav in voiced:
        inputs += ["-i", str(wav)]
    first_voice = 2 if mood != "none" else 1
    for j, (start, _) in enumerate(voiced):
        ms = int(start * 1000)
        filt.append(f"[{first_voice + j}:a]{VOICE_CHAIN},aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{j}]")
    if voiced:
        labels = "".join(f"[v{j}]" for j in range(len(voiced)))
        filt.append(f"{labels}amix=inputs={len(voiced)}:normalize=0,apad=whole_dur={total:.3f}[vo]")
    if mood != "none" and voiced:
        filt += ["[1:a]volume=0.5[m]", "[vo]asplit[v1][v2]",
                 "[m][v1]sidechaincompress=threshold=0.015:ratio=9:attack=20:release=450[d]",
                 "[d][v2]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=9[a]"]
    elif mood != "none":
        filt.append("[1:a]volume=0.6,loudnorm=I=-16:TP=-1.0[a]")
    elif voiced:
        filt.append("[vo]loudnorm=I=-14:TP=-1.0[a]")
    if filt:
        ff(*inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
           "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out))
    else:
        shutil.copy(video, out)


def render(ref: str | Path, out: Path | None = None) -> Result:
    """Renders a reel (a name in the workspace, or a path to its spec file)."""
    spec_path, base = resolve_reel(str(ref))
    reel = load(spec_path)
    build = base / "build"
    build.mkdir(parents=True, exist_ok=True)
    name = spec_path.parent.name if spec_path.stem == "reel" else spec_path.stem
    out = out or base / f"{name}.mp4"

    log(f"voice: {reel.voice}")
    progress("voice", 0, len(reel.beats), voice=reel.voice)
    takes = speak([Line(b.say, b.pronounce or b.say) for b in reel.beats], reel.voice, build / "voice", log=log)
    durs = [round(max(1.6, LEAD + t.seconds + PAD), 2) for t in takes]
    durs[-1] = max(durs[-1], 2.6)
    total = sum(durs)
    starts = [sum(durs[:k]) for k in range(len(durs))]

    log(f"drawing {len(reel.beats)} beats ({total:.1f}s, {reel.format})")
    progress("draw", 0, len(reel.beats), seconds=round(total, 2))
    fmt = formats.get(reel.format)
    parts: list[Path] = []
    with page(fmt.w, fmt.h) as p:
        for k, b in enumerate(reel.beats):
            states, caps = cards.render_beat(p, reel, k, build)
            scene_mp4 = None
            bg = _background(b)
            if bg:
                words = [(w, s) for w, (s, _) in zip(caption_words(b.say), takes[k].word_times)]
                html = scenes.page_html(bg[0], bg[1], style(reel), durs[k], takes[k].seconds, LEAD, words, base)
                scene_mp4 = scenes.render(p, html, durs[k], build / f"{k:02d}_scene.mp4")
            part = build / f"{k:02d}.mp4"
            _clip(k, durs[k], takes[k], states, caps, scene_mp4, starts[k], total, build, reel, part)
            parts.append(part)
            log(f"  beat {k + 1}/{len(reel.beats)} done")
            progress("draw", k + 1, len(reel.beats))
    joined = build / "joined.mp4"
    lst = build / "parts.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined))
    progress("mix")
    _mix(reel, takes, starts, total, joined, build, out)
    cap = out.with_name("caption.txt")
    cap.write_text(caption_text(reel, base), encoding="utf-8")
    log(f"done: {out} ({total:.1f}s)")
    progress("done", 1, 1, video=str(out), seconds=round(total, 2))
    return Result(out, cap, total, [t.score for t in takes])


def preview(ref: str | Path, beat: int, at: float = 0.7) -> Path:
    """A still of one beat (scene + card), `at` of the way through it. Fast: no voice, no video."""
    spec_path, base = resolve_reel(str(ref))
    reel = load(spec_path)
    if not 0 <= beat < len(reel.beats):
        raise IndexError(f"beat {beat} out of range (0..{len(reel.beats) - 1})")
    b = reel.beats[beat]
    build = base / "build" / "preview"
    build.mkdir(parents=True, exist_ok=True)
    from .captions import estimate_seconds, spread

    secs = estimate_seconds(b.say)
    dur = LEAD + secs + PAD
    out = build / f"beat{beat:02d}.png"
    fmt = formats.get(reel.format)
    with page(fmt.w, fmt.h) as p:
        states, _ = cards.render_beat(p, reel, beat, build)
        bg = _background(b)
        if not bg:
            shutil.copy(states[-1], out)
            return out
        words = [(w, s) for w, (s, _) in zip(caption_words(b.say), spread(b.say, secs))]
        html = scenes.page_html(bg[0], bg[1], style(reel), dur, secs, LEAD, words, base)
        still = scenes.still(p, html, dur, dur * at, build / f"beat{beat:02d}_scene.png")
    ff("-i", str(still), "-i", str(states[-1]), "-filter_complex", "[0:v][1:v]overlay=0:0", str(out))
    return out
