# Architecture

The game is split into four small layers:

1. `glyph_city/city.py` stores the deterministic map, props, weather clock, movement and collision.
2. `glyph_city/living.py` advances residents, jobs, conversations and public events. It does not draw anything.
3. `glyph_city/render.py` casts one ray per terminal column, projects walls and sprites, samples ground materials, and returns colored character cells.
4. `glyph_city/terminal.py` owns terminal modes, keyboard events, ANSI encoding and delta updates.

`glyph_city/director.py` creates a read-only camera view for City Watch. It copies camera state while sharing the simulation, so watching never moves or edits the saved player. `glyph_city/audio.py` consumes the current scene and listener orientation and remains optional.

The old implementation remains under `legacy/v1/`. The main project does not import its renderer.

`glyph_city/director.py` keeps one render pose per frame and moves between
shots through collision-checked city corridors. A shot change starts at the
current pose, follows an eased route, and blends heading, lens, and height;
NPC focus is distance-bounded and never teleports the camera through a facade.

`glyph_city/audio.py` loads the generated PCM bank from `assets/audio/` and
cycles through three prebuilt variants for each short cue. Long ambience beds
are streamed continuously, while the native callback or macOS fallback keeps
transitions alive without rebuilding audio for every camera turn.
