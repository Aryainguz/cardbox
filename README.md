<p align="center">
  <img src="site/media/logo.svg" width="72" alt="cardbox logo">
</p>

<h1 align="center">cardbox</h1>

<p align="center">
  <b>Script in. Video out. In your own voice.</b><br>
  Narrated, captioned, animated videos for Reels, Shorts, YouTube and LinkedIn, from one YAML file<br>
  or straight from your AI assistant over MCP.
</p>

<p align="center">
  <a href="https://aryainguz.github.io/cardbox">Website</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#use-it-from-your-ai-assistant-mcp">MCP</a> ·
  <a href="docs/spec.md">Spec reference</a> ·
  <a href="server/">Render API</a>
</p>

<p align="center">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-black">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-black">
  <img alt="go" src="https://img.shields.io/badge/go-1.22%2B-black">
  <img alt="mcp" src="https://img.shields.io/badge/MCP-server-black">
</p>

---

https://github.com/aryainguz/cardbox/raw/main/site/media/promo-vertical.mp4

> **That video was made entirely with cardbox.** The script, the visuals, the music, and the voice: it's a clone, recorded in one minute.

## Why cardbox

Making a short explainer video by hand means scripting, recording, re-recording the line you fluffed, cutting, captioning, animating and syncing it all. cardbox does all of that from a text file:

```yaml
title: How a hash table finds anything instantly
format: vertical          # vertical · landscape · square
theme: midnight           # 7 themes, or any accent color
voice: me                 # your cloned voice · system · none
beats:
  - kind: hook
    text: One step. Any size.
    say: Your phone finds one contact out of ten thousand in a single step.
  - kind: scene
    scene: counter
    head: So the lookup is
    say: Finding Priya takes one step, whether you have ten contacts or ten million.
    params: {to: 1, label: step, on: one}      # fires the moment you say "one"
  - kind: end
    text: Follow for more
    say: Follow for more computer science, explained simply.
```

```bash
cardbox render hash-table      # → hash-table.mp4 + caption.txt
```

## What makes it different

- 🎙️ **Your voice, cloned on your machine.** Read ten short lines in a browser page (about a minute), and every video is narrated in your voice. A consent statement is the first thing recorded.
- 👂 **It checks its own narration.** Every line is transcribed with Whisper and compared with the script. If a word came out slurred or skipped, cardbox re-records that line with a new seed. No more listening to every take.
- ⏱️ **Animations land on the word.** `on: billion` starts a counter the instant you say "billion". Captions highlight each word as it's spoken.
- 🤖 **An MCP server, built in.** Claude, Cursor or any MCP client can write the script, **look at preview frames** before rendering, find images, walk you through voice recording, and render.
- 🖼️ **License-safe images.** Search Openverse and Wikimedia Commons for reusable images only (CC0, public domain, CC BY, CC BY-SA). Credits are written into the post caption automatically.
- 📐 **One script, every platform.** `format: landscape` re-lays out every beat for YouTube; `square` for the LinkedIn feed.
- 🎵 **A soundtrack with no licensing questions.** A music bed is synthesized for each video (calm, upbeat or tense), with a hit on every cut and ducking under the voice.
- 🛠️ **Runs as a service.** A Go [render API](server/) with a worker pool, live progress over SSE, signed webhooks, idempotency and Prometheus metrics.

## Quick start

Requirements: Python 3.10+, `ffmpeg`, and Chrome or Chromium.

```bash
pip install cardbox
python -m playwright install chromium   # skip if Google Chrome is installed
cardbox doctor                          # checks ffmpeg, the browser and voice support

cardbox new my-first-video              # creates ~/Cardbox/reels/my-first-video/reel.yaml
cardbox preview my-first-video 1        # a PNG of beat 1, in a couple of seconds
cardbox render my-first-video           # the full video
```

The template uses the operating system's voice, so it works with no extra installs. To narrate in **your** voice:

```bash
pip install "cardbox[voice]"            # Chatterbox + Whisper (PyTorch; GPU or Apple Silicon recommended)
cardbox voice record me                 # opens the recording studio in your browser
cardbox voice test "Hello, this is my cloned voice." --voice me
```

Then set `voice: me` in any spec.

> The voice stack is heavy. If you'd rather keep PyTorch out of your main environment, install `cardbox[voice]` in a separate one and point `CARDBOX_VOICE_PYTHON` at its interpreter.

## Use it from your AI assistant (MCP)

Add cardbox to your client's MCP config:

```json
{
  "mcpServers": {
    "cardbox": { "command": "cardbox", "args": ["mcp"] }
  }
}
```

- **Claude Desktop:** `claude_desktop_config.json` · **Claude Code:** `claude mcp add cardbox -- cardbox mcp` · **Cursor:** `.cursor/mcp.json`

Then just ask: *"Make a 40-second vertical video explaining how DNS works, in my voice."*

| Tool | What it does |
| --- | --- |
| `guide` | How to write a good video: spec format, scenes, writing rules |
| `create_reel` / `get_reel` / `list_reels` | Save and read specs (validation errors come back in plain English) |
| `preview_beat` | Returns a **frame image** so the assistant can see its work before rendering |
| `render_reel` | Renders the MP4 and the post caption, and flags lines the voice may have fumbled |
| `search_images` / `add_image` | Openly licensed images, downloaded and credited |
| `voice_status` / `voice_record` / `voice_test` | Record, check and try your cloned voice |
| `find_icons` / `spec_schema` | 1,900 Lucide icons; the full JSON Schema |

## Formats, themes and styles

| Option | Values |
| --- | --- |
| `format` | `vertical` 1080×1920 (Reels, Shorts, TikTok) · `landscape` 1920×1080 (YouTube, LinkedIn) · `square` 1080×1080 (feeds) |
| `theme` | `midnight` · `ember` · `forest` · `neon` · `sunset` · `mono` · `paper` (light) |
| `accent` | any hex color, overriding the theme's accent |
| `font` | `sans` (Inter) · `mono` (JetBrains Mono) |
| `captions` | `highlight` · `box` · `minimal` · `none` |
| `music` | `calm` · `upbeat` · `tense` · `none` |

**Beat kinds:** `hook`, `text`, `stat`, `list`, `scene`, `end`. Hooks and text beats can take a `background` (an image with a slow push-in, or any scene).

**Scenes:** `counter` · `donut` · `bars` · `flow` · `terminal` · `mesh` · `grid` · `photo`. See [docs/spec.md](docs/spec.md) for every parameter.

**Pronunciation:** captions show `say`, but the voice reads `pronounce` when you set it. Write `say: SongsPK` with `pronounce: Songs P K`.

## Render API (Go)

[`server/`](server/) is an HTTP service that queues renders and streams progress:

```bash
cd server && go run ./cmd/cardbox-server     # or: docker compose up
curl -X POST localhost:8080/v1/renders -H "Content-Type: application/yaml" --data-binary @video.yaml
curl -N localhost:8080/v1/renders/<id>/events   # live progress (SSE)
```

It has a bounded worker pool with backpressure, cancellation, graceful drain, SQLite persistence with crash recovery, idempotency keys, reuse of identical renders, HMAC-signed webhooks with retries, API keys, per-key rate limits and Prometheus metrics. Details are in [server/README.md](server/README.md).

## How it works

```
spec.yaml ─► voice (clone · verify with Whisper · retry) ─► word timings
          ─► cards (HTML) + scenes (canvas, cued to words) in a headless browser
          ─► per-beat clips (captions word by word, progress bar) ─► concat
          ─► synthesized music, ducked under the voice ─► video.mp4 + caption.txt
```

Everything runs locally. Your recordings and your voice model never leave your machine.

## Responsible use

Voice cloning is powerful. cardbox records a consent statement as the first take of every voice profile, and won't build a voice without it. **Only clone your own voice, or a voice you have explicit permission to use.** Don't use cardbox to impersonate anyone or to mislead people about who is speaking.

## Contributing

New scenes, themes and caption styles are the easiest place to start: each scene is a single function in [`src/cardbox/scenes/library.js`](src/cardbox/scenes/library.js). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- [Chatterbox](https://github.com/resemble-ai/chatterbox) (MIT) for voice cloning, and [Whisper](https://github.com/openai/whisper) (MIT) for listening back.
- [Lucide](https://lucide.dev) icons (ISC), plus [Inter](https://rsms.me/inter/) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/) (SIL OFL).
- [Openverse](https://openverse.org) and [Wikimedia Commons](https://commons.wikimedia.org) for openly licensed images.

MIT licensed.
