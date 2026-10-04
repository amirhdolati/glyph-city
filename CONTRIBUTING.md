# Contributing

Glyph City is intentionally small and readable. Changes should keep the terminal experience responsive, deterministic when a seed is supplied, and usable without optional audio or preview dependencies.

## Local checks

```sh
python3 -m compileall -q glyph_city tests
python3 -m unittest discover -s tests -v
python3 main.py --profile --profile-frames 30
```

When changing the renderer, include a before/after preview in the pull request. Use `python3 tools/make_previews.py` to refresh the gallery. When changing controls, test both a Kitty-compatible terminal and a legacy terminal that only sends key repeats.

## Code guidelines

- Keep world simulation separate from rendering and terminal I/O.
- Preserve the seeded behavior of the city and write tests for new deterministic rules.
- Keep optional packages optional; the game must still start when audio and preview packages are absent.
- Use short, named systems instead of adding more state to the main game loop.
