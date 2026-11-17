# Examples

| Example | What it shows | Make it |
| --- | --- | --- |
| [`wifi.txt`](wifi.txt) | Plain text, no YAML: hook, a number card, an ending | `cardbox make examples/wifi.txt --render` |
| [`hash-table/reel.yaml`](hash-table/reel.yaml) | A full spec: bars, a flow and a counter, cued to words | `cardbox render examples/hash-table/reel.yaml` |
| [`promo/promo-explainer.yaml`](promo/promo-explainer.yaml) | The 16:9 explainer on the website: logo, chat, script, voice and format scenes | `cardbox render examples/promo/promo-explainer.yaml` |
| [`promo/promo-reel.yaml`](promo/promo-reel.yaml) | A vertical, hook-first reel | `cardbox render examples/promo/promo-reel.yaml` |

The promo examples narrate with a recorded voice named `inguz`. Change `voice:` to `auto` (or your own voice's
name) to render them yourself.

Try any of them in another format or theme without touching the file:

```bash
cardbox make examples/wifi.txt --format square --theme paper --render
```
