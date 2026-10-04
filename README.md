# Glyph City: Afterlight

![City Watch rain preview](docs/media/city-watch.gif)

Glyph City: Afterlight is a living ASCII city that keeps running when nobody is touching the keyboard. Watch rain move across Moonwater, follow residents through their routines, look through furnished shop windows, or take control and walk wherever you like.

![Night rain](docs/media/night-rain.png)
![Day market](docs/media/day-market.png)
![Storm canal](docs/media/storm-canal.png)

The project is a terminal-first zero-player simulation with an optional first-person walk mode. It runs on macOS, Linux, and WSL terminals that support ANSI colors. A terminal around 120 columns by 40 rows gives the city enough room to breathe.

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
python3 main.py --max-width 120 --fps 24
```

## What is in the city

- A deterministic 120 × 120 city with six districts and discoverable landmarks: Willow Gardens, Lantern Market, Copper Lane, Glass Quarter, Afterlight Crossing, and Moonwater Canal.
- A variable-height ASCII ray caster with depth, fog, local lamp pools, wet pavement, water reflections, rain, clouds, stars, dusk colors, and storm flashes.
- Ground-floor glass windows with furnished interiors: cafes, restaurants, bookshops, vinyl stores, hotels, bars, lounges, and mature 18+ venues represented through environmental silhouettes and lighting.
- A day and night clock, clear/rain/storm/mist weather, gradual wetness, umbrella and shelter behavior, an automatic canal boat, a playable cafe room, a journal, a map, photo mode, and a persistent album.
- City Watch, a zero-player mode with named residents, jobs, destinations, queues, shelters, conversations, staged public events, and cinematic camera shots that can follow an active NPC.
- Staged events such as parcel delivery, street music, shared umbrellas, and neighborhood blackouts. Every event has several beats and changes what the participants are doing.
- A layered soundscape with rain, wind, water, traffic, leaves, footsteps, birds, music, doors, thunder, stereo attenuation, and camera-aware direction when a native backend is available.
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
| C | Toggle RGB and 256-color output |
| X / Escape / Ctrl-C | Exit |

In the settings panel, numeric values change with visible steps and save immediately. The settings file is kept separately from the world save so visual preferences cannot corrupt a walk.

## Previews and development tools

The committed gallery lives in [`docs/media`](docs/media). Rebuild the PNG stills and animated GIF with:

```sh
python3 tools/make_previews.py
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

The design and implementation notes are available in [`ROADMAP.fa.md`](ROADMAP.fa.md) and [`RENDERING_GAMEPLAY_CONTROLS.fa.md`](RENDERING_GAMEPLAY_CONTROLS.fa.md).

## License and project status

This is an active experimental terminal simulation. The previous game snapshot is preserved, tests cover rendering, terminal input, saves, navigation, interiors, City Watch, and optional systems, and every major milestone is committed so the project can be recovered or compared easily. See [`RENDASCII_LICENSE.txt`](RENDASCII_LICENSE.txt) for the preserved engine license.
