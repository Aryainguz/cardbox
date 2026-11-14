"""The MCP server: lets any AI assistant (Claude, Cursor, ChatGPT desktop, ...) make reels with cardbox.

The assistant writes the script as a reel spec, can look at frames before rendering (preview_beat
returns an image), finds openly licensed images, and walks you through recording your voice.

Run with `cardbox mcp` (stdio). Nothing is printed to stdout except the protocol.
"""

from __future__ import annotations

import json

import yaml
from mcp.server.mcpserver import Image, MCPServer
from pydantic import ValidationError

from . import icons, media, scenes, spec
from .render import preview, render
from .voice.engines import has_voice_stack
from .voice.profile import PROMPTS, Profile
from .voice.studio import start as start_studio
from .workspace import home, reel_dir, resolve_reel, slug

mcp = MCPServer(
    "cardbox",
    instructions="Makes narrated, captioned short videos (reels/shorts) from a script. Call `guide` first, "
    "then create_reel, preview_beat to look at frames, and render_reel.",
)

GUIDE = """# Making a reel with cardbox

A reel is YAML: a title, settings, and a list of beats. Each beat is one thing on screen plus one
spoken line (`say`). The voice sets the timing: a beat lasts as long as its line.

```yaml
title: Why your Wi-Fi slows down at night
handle: "@yourname"          # shown on every card
theme: midnight              # midnight | ember | forest | mono
voice: auto                  # auto (your voice if recorded), a voice name, "system", or "none"
caption: The post caption. Line one is what people see before "more".
hashtags: [wifi, networking, techexplained]   # up to 5
beats:
  - kind: hook               # first 2 seconds: one bold claim or question
    eyebrow: Networking 101
    text: Your Wi-Fi isn't slow. It's crowded.
    say: Your Wi-Fi isn't slow at night. It's crowded. Here's what's actually happening.
    background: {image: media/router.jpg}        # optional: image or {scene, params}
  - kind: scene
    scene: bars
    head: Everyone's on at 9 PM
    say: At nine PM, every phone on your street is streaming at once.
    params: {bars: [{label: 9 AM, value: 20}, {label: 9 PM, value: 95, on: nine}], unit: "%"}
  - kind: stat
    value: "2.4 GHz"
    label: has only 3 channels that don't overlap
    say: And the older band only has three channels that don't overlap.
  - kind: list
    head: Three fixes
    items: [{icon: wifi, text: Switch to 5 GHz}, {icon: router, text: Move the router up high}, Change the channel]
    say: Switch to five gigahertz, move your router up high, or change the channel.
  - kind: end
    text: Follow for more
    say: Follow for more tech, explained simply.
```

Beat kinds: hook, text (text, sub, icon, background), stat (value, label, icon), list (head, items),
scene (scene, head, params), end. Any beat can set `pronounce` to respell a word for the voice only
(captions keep `say`), e.g. say "SongsPK" but pronounce "Songs P K".

YAML tip: inside inline {...} maps, quote any value that contains a comma:
{text: "Reels, Shorts, TikTok"} — otherwise YAML splits it into separate keys.

Timing animations to speech: in scene params, any `on` takes a word from the line ("on": "nine")
and fires when that word is spoken, or a number 0..1 (fraction of the line).

Writing rules that make reels work:
- Hook in the first line: concrete, surprising, under ~10 words on screen.
- One idea per beat, 1 to 3 short sentences spoken. 6 to 10 beats, 30 to 60 seconds total.
- Every number must be true and sourced. Say numbers the way you'd speak them ("twenty ten").
- End with a reason to comment or follow.

Workflow: make_video (plain text, quickest) or create_reel (full spec) → preview_beat (look at a few frames)
→ fix → render_reel. Upgrade plain beats to animated scenes where a picture explains it better.
Use search_images + add_image for real photos (only reusable licenses; credits are added for you).
For the user's own voice: voice_status, then voice_record (they read ~10 short lines in a browser page).
"""


def _errors(e: ValidationError) -> str:
    return "\n".join(f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())


@mcp.tool()
def guide() -> str:
    """How to write a reel spec, with an example, the beat kinds and the writing rules. Read this first."""
    return GUIDE + "\n\nScenes:\n" + "\n".join(f"- {k}: {v}" for k, v in scenes.CATALOG.items())


@mcp.tool()
def spec_schema() -> str:
    """The full JSON Schema of a reel spec."""
    return json.dumps(spec.schema(), indent=1)


@mcp.tool()
def find_icons(query: str, limit: int = 30) -> list[str]:
    """Icon names (Lucide) matching a word, for `icon` fields and scene params. Example: query='lock'."""
    q = query.lower().strip()
    return [n for n in icons.names() if q in n][:limit]


@mcp.tool()
def create_reel(name: str, spec_yaml: str) -> str:
    """Creates or replaces a reel from a YAML (or JSON) spec. Returns a summary, or the validation errors to fix."""
    try:
        reel = spec.parse(spec_yaml)
    except ValidationError as e:
        return "The spec has problems:\n" + _errors(e)
    except (ValueError, yaml.YAMLError) as e:
        return f"Couldn't read the spec: {e}"
    unknown = [b.scene for b in reel.beats if isinstance(b, spec.SceneBeat) and b.scene not in scenes.CATALOG]
    if unknown:
        return f"Unknown scene(s): {', '.join(unknown)}. Available: {', '.join(scenes.CATALOG)}"
    d = reel_dir(name)
    (d / "reel.yaml").write_text(spec.dump(reel), encoding="utf-8")
    words = sum(len(b.say.split()) for b in reel.beats)
    return (f"Saved reel '{slug(name)}' ({len(reel.beats)} beats, about {words / 2.6:.0f}s spoken) at {d / 'reel.yaml'}.\n"
            "Next: preview_beat to check frames, then render_reel.")


@mcp.tool()
def make_video(name: str, script: str, format: str = "vertical", theme: str = "midnight", voice: str = "auto") -> str:
    """Creates a video from a plain-text script: one paragraph per beat, the first is the hook, the last is the
    closing card. A line starting with '# ' sets a beat's on-screen headline; '# 8.8% of the music' makes a stat card.
    A line '@ file.jpg' (or .mp4) puts a file from the video's media/ folder behind that beat (use add_image first).
    Easiest way to start; refine afterwards with get_reel/create_reel (scenes, images, timing)."""
    from .script import from_text

    try:
        reel = from_text(script, media_dir=reel_dir(name) / "media", format=format, theme=theme, voice=voice)
    except (ValueError, ValidationError) as e:
        return f"Couldn't build the video: {e}"
    d = reel_dir(name)
    (d / "reel.yaml").write_text(spec.dump(reel), encoding="utf-8")
    return (f"Saved '{slug(name)}' with {len(reel.beats)} beats. Headlines: "
            + " | ".join(getattr(b, "text", getattr(b, "value", "")) for b in reel.beats)
            + "\nNext: preview_beat, or upgrade beats to animated scenes with create_reel, then render_reel.")


@mcp.tool()
def get_reel(name: str) -> str:
    """The current spec of a reel, as YAML."""
    path, _ = resolve_reel(name)
    return path.read_text(encoding="utf-8")


@mcp.tool()
def list_reels() -> list[dict]:
    """All reels in the workspace, with whether each has been rendered."""
    root = home() / "reels"
    out = []
    for d in sorted(root.iterdir()) if root.exists() else []:
        if (d / "reel.yaml").exists():
            out.append({"name": d.name, "rendered": (d / f"{d.name}.mp4").exists()})
    return out


@mcp.tool()
def preview_beat(name: str, beat: int, at: float = 0.7) -> Image:
    """A still frame of one beat (0-based), `at` of the way through it (0..1). Look before you render."""
    return Image(path=str(preview(name, beat, at)))


@mcp.tool()
def render_reel(name: str) -> str:
    """Renders the reel to MP4 (1080x1920, 30 fps) and writes caption.txt. Takes a few minutes."""
    r = render(name)
    weak = [i for i, s in enumerate(r.voice_scores) if s is not None and s < 0.97]
    note = f"\nLines where the voice may be off (re-word or add `pronounce`): {weak}" if weak else ""
    return (f"Video: {r.video}\nLength: {r.seconds:.1f}s\nCaption file: {r.caption}\n\n"
            f"{r.caption.read_text(encoding='utf-8')}{note}")


@mcp.tool()
def search_images(query: str, limit: int = 8) -> list[dict]:
    """Openly licensed images (CC0, public domain, CC BY, CC BY-SA) from Openverse and Wikimedia Commons."""
    return [{"id": i.id, "title": i.title, "thumbnail": i.thumbnail, "size": f"{i.width}x{i.height}",
             "license": i.license, "author": i.author} for i in media.search(query, limit)]


@mcp.tool()
def add_image(reel: str, image_id: str, name: str) -> str:
    """Downloads an image from search_images into a reel's media/ folder. Use the returned path as `image`."""
    path, img = media.fetch(image_id, reel_dir(reel), name)
    return f"Saved as media/{path.name} ({img.license}, {img.author or 'unknown author'}). Use image: media/{path.name}"


@mcp.tool()
def voice_status(voice: str = "default") -> dict:
    """Whether a voice is recorded and ready to clone, and whether the cloning models are installed."""
    st = Profile(voice).status()
    st["models_installed"] = has_voice_stack()
    st["voices"] = Profile.all()
    return st


@mcp.tool()
def voice_record(voice: str = "default") -> str:
    """Opens the recording studio in the user's browser. Tell them to read each line naturally; about a minute."""
    url = start_studio(voice)
    return (f"The recording studio is open at {url}\n"
            f"Ask the user to: tick the consent box, then read the {len(PROMPTS)} short lines out loud "
            "(Record, read, Stop). Each take is checked for noise and level instantly. "
            "Call voice_status to see progress; 4 good takes are enough, all 10 sounds best.\n"
            "Only the speaker themself may record their voice for cloning.")


@mcp.tool()
def voice_test(text: str, voice: str = "default") -> str:
    """Speaks one line in a voice and reports what the speech checker heard. Returns the audio file path."""
    from .voice.engines import Line, speak

    take = speak([Line(text, text)], voice, home() / "voices" / slug(voice) / "tests")[0]
    score = "n/a" if take.score is None else f"{take.score:.0%}"
    return f"Audio: {take.wav}\nHeard: {take.heard!r}\nMatch: {score}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
