# Glyph City: Afterlight

![City Watch: Moonwater at dusk and in the rain](docs/media/city-watch.gif)

Glyph City: Afterlight is a living ASCII city that keeps running when nobody is touching the keyboard. Watch rain move across Moonwater, follow residents through their routines, look through furnished shop windows, or take control and walk wherever you like.

The 20-second preview visits the canal from the boat and bridge, then returns
in nighttime rain. These are captures from the game's RGB renderer, with
real-time motion and three editorial cuts. For the full RGB gradients, open
the [lossless animated WebP](docs/media/city-watch.webp). GIF has a limited palette.

![Moonwater at dusk: building reflections across the canal](docs/media/moonwater-dusk.png)
![Moonwater at night: rain and reflected window light](docs/media/moonwater-night.png)
![Bridge overlook in the afterglow](docs/media/bridge-afterglow.png)

See the [complete screenshot gallery](docs/preview-gallery.md) for gardens,
shop interiors, the market, rooftops, and the RGB / 256-color comparison.

The project is a terminal-first zero-player simulation with an optional first-person walk mode. It runs on macOS, Linux, and WSL terminals that support ANSI colors. For the detailed view, aim for 160–180 columns and 50–60 rows.

## Run it

```sh
git clone https://github.com/amirhdolati/glyph-city.git
cd glyph-city
python3 main.py --watch --time night --weather rain
```

Python 3.10+ is required. The game renderer uses only the Python standard library. `numpy` is optional and enables the higher-quality procedural audio mixer; without it, the game stays playable with silent audio.

```sh
# Optional audio and preview tooling
python3 -m pip install numpy Pillow
```

Useful starts:

```sh
python3 main.py                         # walking mode
python3 main.py --watch                  # zero-player City Watch
python3 main.py --watch --time night --weather rain
python3 main.py --time 12 --weather clear
python3 main.py --time 20 --weather storm --seed 42
python3 main.py --256                   # force 256-color output
python3 main.py --watch --truecolor      # smoother colors on a 24-bit terminal
python3 main.py --max-width 120 --fps 24
python3 main.py --diagnose              # inspect this terminal and saved settings
```

### Get the detailed terminal view

Keep your existing zsh and Oh My Zsh setup. The terminal app draws the game;
the shell starts it. For macOS, [Ghostty](https://ghostty.org/docs/features)
offers GPU rendering, and iTerm2 also supports RGB color. Apple Terminal on
macOS Tahoe 26 supports RGB; older Apple Terminal versions use 256 colors.
Auto palette selection accounts for this difference.

1. Maximize the terminal window. Start with Menlo at 11–13 pt and reduce the
   font size until the window has at least 160 columns and 50 rows.
2. Use an opaque background and disable font ligatures, so ASCII strokes keep
   their individual shapes. Keep character spacing at its normal setting.
3. In the game's `I` settings, use **Palette: auto**, **Truecolor: on**,
   **Render width: 180**, **Cell aspect: 0.5**, **Night contrast: 1.0** and
   **FPS: 24**. For quiet viewing, switch camera bob and storm flashes off.
4. Restart the game after editing the settings file outside the game.

```sh
python3 main.py --watch --time dusk --weather rain --max-width 180 --max-height 90
```

The width and height limits cannot add cells to a small terminal window.
`--diagnose` reports the actual available cells, chosen colors, saved settings
and suggestions. A 180 × 59 window displays the 180 × 56 scene used by the
gallery stills, plus its three status rows. Higher resolution takes more CPU;
reduce width to 160 if motion is uneven. FPS is a limit, not a guarantee.

## What is in the city

- A deterministic 120 × 120 city with six districts, a denser population of named residents, and discoverable landmarks: Willow Gardens, Lantern Market, Copper Lane, Glass Quarter, Afterlight Crossing, and Moonwater Canal.
- A variable-height ASCII ray caster with depth, fog, local lamp pools, wet pavement, water reflections, rain, clouds, stars, dusk colors, and storm flashes.
- Ground-floor glass windows with furnished interiors: cafes, restaurants, bookshops, vinyl stores, hotels, bars, lounges, and mature 18+ venues represented through environmental silhouettes and lighting.
- A day and night clock, clear/rain/storm/mist weather, gradual wetness, umbrella and shelter behavior, an automatic canal boat, a playable cafe room, a journal, a map, photo mode, and a persistent album.
- City Watch, a zero-player mode with named residents, jobs, destinations, queues, shelters, conversations, staged public events, and ten cinematic camera shots, including elevated Glass Quarter and bridge overlooks.
- City Watch camera moves are collision-aware: manual and automatic shot changes use a slow curved transfer from the current pose, with bounded subject focus and no hard teleport between viewpoints.
- Staged events such as parcel delivery, street music, shared umbrellas, and neighborhood blackouts. Every event has several beats and changes what the participants are doing.
- A layered soundscape with long rain, wind, water, traffic, and leaves beds plus cached multi-variant footsteps, birds, music, doors, thunder, car passes, rain hits, and drips. The generated PCM bank lives in [`assets/audio`](assets/audio) and is reused at runtime without synthesizing SFX during gameplay.
- A settings panel inside the game for palette, Truecolor, FPS, render width, cell aspect, mouse sensitivity, camera bob, night contrast, storm flashes, and volume.

## Controls

| Key | Action |
| --- | --- |
| W / A / S / D | Walk and strafe |
| Q / E or Left / Right | Turn |
| Shift + movement | Sprint |
| I | Open settings; W/S selects and A/D or Left/Right edits |
| O | Toggle City Watch and walking |
| [ / ] | Previous/next cinematic shot in City Watch |
| U | Umbrella |
| R / N | Toggle rain / cycle weather |
| Y / T | Skip time / pause the clock |
| F | Pocket lantern |
| Space | Pause or resume the world for a photo |
| P / J | Capture a photo / open the album |
| K / M | Open journal / map |
| H | Controls overlay |
| B | Identify visible objects, residents, shops, and ground materials |
| C | Toggle RGB and 256-color output |
| X / Escape / Ctrl-C | Exit |

In the settings panel, numeric values change with visible steps and save immediately. The settings file is kept separately from the world save so visual preferences cannot corrupt a walk.

Trees have leafy crowns, lamps have thin poles, and benches, fountains, cars,
boats, and tea stalls retain distinct silhouettes. Near residents carry visible
books, cameras, parcels, cups, or instruments. Shop displays distinguish records,
books, flowers, hotel beds, and cafe furniture. `B` adds optional object captions
and a material guide; captions avoid overlap and hidden objects. A terminal of
160 columns by 50 rows or larger shows more of these details. Close trees,
planters, benches and fountains have additional authored shapes, thin strokes,
and shaded solid surfaces. Shop interiors have local lighting and recessed
frames; lamps and signs cast a restrained glow, and elevated views reveal
solid roof surfaces.

The status bar shows `RGB` or `256`. The 256-color renderer keeps the sky's hue
consistent; RGB allows smoother lighting and fog gradients. `C` switches color
mode during play. The [gallery](docs/preview-gallery.md) includes both output
palettes, and `--shot --256` exports the actual terminal palette to HTML.

## Previews and development tools

The committed gallery lives in [`docs/media`](docs/media). Rebuild the PNG stills and animated GIF with:

```sh
python3 tools/make_previews.py
```

Rebuild the deterministic audio bank after changing a sound recipe:

```sh
python3 tools/make_audio.py
```

Export a browser preview or an ANSI snapshot directly from the renderer:

```sh
python3 main.py --shot --time night --weather rain --output previews/night-rain.html
python3 main.py --profile --time night --weather rain --profile-frames 60
python3 -m unittest discover -s tests -v
```

Photos captured in-game are stored beside the save file in a `photos/` directory. Each photo includes an HTML view, an ANSI frame, and JSON metadata with district, weather, time, and seed.

## Renderer architecture

The main renderer is a small dependency-free Python implementation in [`glyph_city/render.py`](glyph_city/render.py). It performs camera ray casting, wall projection, depth ordering, material shading, ground sampling, sprite projection, transparent shop panes, and ANSI cell encoding. [`glyph_city/interiors.py`](glyph_city/interiors.py) traces room furniture behind the glass. [`glyph_city/living.py`](glyph_city/living.py) owns residents and staged events, while [`glyph_city/director.py`](glyph_city/director.py) owns cinematic observation.

The old RendASCII implementation is preserved in [`legacy/v1`](legacy/v1) and can still be launched:

```sh
python3 main.py --classic
```

The design and implementation notes are available in [`ROADMAP.md`](ROADMAP.md), [`RENDERING_GAMEPLAY_CONTROLS.md`](RENDERING_GAMEPLAY_CONTROLS.md), and [`docs/architecture.md`](docs/architecture.md).

## License and project status

This is an active experimental terminal simulation. The previous game snapshot is preserved, tests cover rendering, terminal input, saves, navigation, interiors, City Watch, and optional systems, and every major milestone is committed so the project can be recovered or compared easily. See [`RENDASCII_LICENSE.txt`](RENDASCII_LICENSE.txt) for the preserved engine license.
