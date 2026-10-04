# Architecture

The game is split into four small layers:

1. `glyph_city/city.py` stores the deterministic map, props, weather clock, movement and collision.
2. `glyph_city/living.py` advances residents, jobs, conversations and public events. It does not draw anything.
3. `glyph_city/render.py` casts one ray per terminal column, projects walls and sprites, samples ground materials, and returns colored character cells.
4. `glyph_city/terminal.py` owns terminal modes, keyboard events, ANSI encoding and delta updates.

`glyph_city/director.py` creates a read-only camera view for City Watch. It copies camera state while sharing the simulation, so watching never moves or edits the saved player. `glyph_city/audio.py` consumes the current scene and listener orientation and remains optional.

The old implementation remains under `legacy/v1/`. The main project does not import its renderer.
