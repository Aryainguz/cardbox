# Spec reference

A cardbox video is one YAML (or JSON) file. Each **beat** is one thing on screen plus one spoken line.
The spoken line sets the timing: a beat lasts as long as it takes to say it.

## Top level

| Field | Default | Notes |
| --- | --- | --- |
| `title` | (required) | Used for the caption if `caption` is empty |
| `format` | `vertical` | `vertical` (1080×1920), `landscape` (1920×1080), `square` (1080×1080). Aliases: `reel`, `shorts`, `youtube`, `16:9`, `1:1`, `feed` |
| `handle` | | Shown on every card and on the end card, e.g. `"@you"` |
| `theme` | `midnight` | `midnight`, `ember`, `forest`, `neon`, `sunset`, `mono`, `paper` |
| `accent` | | Hex color overriding the theme accent, e.g. `"#22C55E"` |
| `font` | `sans` | `sans` (Inter) or `mono` (JetBrains Mono) |
| `captions` | `highlight` | `highlight`, `box`, `minimal`, `none` |
| `voice` | `default` | A recorded voice name, `system`, or `none` (silent; timings estimated) |
| `music` | `calm` | `calm`, `upbeat`, `tense`, `none` |
| `caption` | | The post caption written to `caption.txt` |
| `hashtags` | | Up to 5 |
| `beats` | (required) | The list below |

Every beat has `say` (the spoken line; captions show exactly these words) and may have `pronounce`
(a respelling the voice reads instead, e.g. `pronounce: M C P` for `say: MCP`).

## Beat kinds

```yaml
- kind: hook            # the opening: one bold claim
  eyebrow: Small caps line above
  text: The headline
  say: ...
  background: {image: media/photo.jpg}        # optional; or {scene: counter, params: {...}}

- kind: text
  text: Headline
  sub: Smaller line under it
  icon: rocket                                # any Lucide icon name
  background: ...                             # optional
  say: ...

- kind: stat
  value: "8.8%"
  label: of the music came from the servers
  icon: server
  say: ...

- kind: list            # items appear one by one across the line
  head: Three fixes
  items: [Plain text, {icon: wifi, text: With an icon}]
  say: ...

- kind: scene           # an animated scene with a headline
  scene: counter
  head: Headline above the animation
  params: {...}
  say: ...

- kind: end
  text: Follow for more
  say: ...
```

## Timing animations to speech

Anything in scene params that takes `on` accepts:

- a **word** from the beat's `say`: it fires when that word is spoken (`on: billion`)
- a **number** from 0 to 1: that fraction of the way through the line (`on: 0.5`)
- nothing: items are spread evenly across the line

## Scenes

### counter
A number counting to its value. `to` (required), `from`, `decimals`, `prefix`, `unit`, `label`, `ring` (bool),
`max` (ring full scale), `on`, `seconds` (count duration, default 1.6), `play` (true or a label: a waveform
starts when the count lands), `alarm` (bool: turns red when done).

```yaml
params: {to: 265, unit: ms, label: to start a song, ring: true, max: 1000, on: typical, play: true}
```

### donut
Parts of a whole. `segments: [{label, value, color?, on?, display?}]`, `center: {value, label}`, `unit`.

### bars
Comparison bars. `bars: [{label, value, note?, on?}]`, `unit`, `highlight` (index, default: last).

### flow
A vertical chain of steps with packets moving down. `nodes: [{icon, label, sub?, on?, color?}]`,
`bad` (index from which links turn red).

### terminal
Commands typing out. `title`, `lines: [{text, on?, color?, output?}]`. Output lines appear instantly.

### mesh
Peers passing pieces of data. `peers` (count), `hub` (label of an optional server that fades),
`you` (label on the centre node), `handoff` (when the hub fades), `icon`, `hubIcon`.

### grid
k of n icons light up. `n`, `k`, `cols`, `icon`, `result: {text, on}`.

### photo
An image in a framed card with a slow push-in, or full-bleed with `full: true` (used for `background`).
`image` (path relative to the spec), `from`/`to` crops as `[x, y, width]` fractions of the image,
`label: {text, on, color}`, `stamp: {text, on, color}` (a rubber stamp slamming down).

## YAML tips

- Quote values with commas inside inline maps: `{text: "Reels, Shorts, TikTok"}`.
- `on:` stays a key (cardbox reads YAML booleans only as `true`/`false`).
- Numbers you want spoken naturally should be written as words in `say` ("twenty ten").
