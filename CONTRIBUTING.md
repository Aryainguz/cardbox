# Contributing

Thanks for helping! Small, focused pull requests are easiest to review.

## Setup

```bash
git clone https://github.com/aryainguz/cardbox && cd cardbox
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
cardbox doctor
pytest && ruff check src tests
(cd server && go test -race ./...)
```

## Good first contributions

- **A new scene.** Add one function to `src/cardbox/scenes/library.js` (design it in the 1080-wide stage,
  content between y 330 and 1290, so it works in every format), describe its params in `CATALOG` in
  `src/cardbox/scenes.py` and in `docs/spec.md`, and add an example beat to `examples/`.
- **A theme.** Add a palette to `src/cardbox/themes.py` and its name to `Theme` in `spec.py`.
- **A caption style.** Add a `.cap.<style>` rule in `cards.py` and the name to `captions` in `spec.py`.
- **A music mood.** Add an entry to `MOODS` in `music.py`.

Check your change visually with `cardbox preview <spec> <beat>` in all three formats.

## Guidelines

- Every number in an example must be true.
- No copyrighted media in the repo: images in examples must be openly licensed, with credits.
- Keep the voice features consent-first.
