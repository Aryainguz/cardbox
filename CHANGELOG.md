# Changelog

## 0.1.1

- README images and links now work on PyPI (absolute URLs).

## 0.1.0 (first release)

- **The app:** run `cardbox` and it opens in your browser. Write a script, choose format and style, add images or
  clips, record your voice, preview frames and render, with no commands.
- **Plain-text scripts:** one paragraph per beat; `# headline`, `# 8.8% label` stat cards and `@ file` media lines.
  No paid AI needed.
- **Formats:** vertical (9:16), landscape (16:9) and square (1:1) from the same script.
- **Style:** 7 themes, any accent color, sans or mono, 4 caption styles, 3 generated music moods.
- **Voice:** record about a minute (consent first), clone it locally, and every line is transcribed and re-recorded
  if a word comes out wrong. The computer's voice and silent previews also work.
- **13 animated scenes**, cued to spoken words: counter, donut, bars, flow, terminal, mesh, grid, photo, logo, chat,
  script, voice, formats.
- **Media:** your own images and video clips as backgrounds; openly licensed image search (Openverse, Wikimedia
  Commons) with credits written into the caption.
- **MCP server** with 14 tools, including `make_video` (plain text) and `preview_beat` (frames the AI can see).
- **Render API (Go):** worker pool, SSE progress, idempotency, content-hash reuse, signed webhooks, API keys,
  rate limits, Prometheus metrics, crash recovery.
