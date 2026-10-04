# Glyph City: Afterlight Roadmap

## Product direction

Glyph City is a terminal-first living city. It should be enjoyable as a zero-player ambient simulation that can stay open for hours, while still offering an optional walk, photo, journal, and story experience.

The design priorities are:

1. A readable, stable terminal renderer.
2. Residents with visible routines and small stories.
3. Cinematic observation that finds interesting moments.
4. Responsive sound and weather.
5. Optional deeper interaction without interrupting the ambient experience.

## Current milestone

The current branch includes the seeded city, variable-height ray caster, day/night lighting, rain, storm and mist, reflective ground, transparent furnished shop windows, a cafe interior, canal boat, photo album, journal, map, City Watch, named residents, staged events, cinematic cameras, optional audio, and in-game settings.

## Roadmap packages

### P0 — Product foundation

- SAVE-01: stable save schema and identifiers.
- SAVE-02: atomic saves with a previous valid backup.
- SAVE-03: start menu and Continue/New Walk flow.
- SET-01: editable in-game settings and persistent preferences.
- UI-01: modal panels, keyboard protocol detection, and terminal recovery.
- PERF-01: deterministic render and update profiling.

### P1 — Walking stories

- INT-01: select the nearest visible interaction.
- INT-02: small actions at benches, shops, docks, and landmarks.
- JRN-01: journal entries with map targets.
- STORY-01: short neighborhood stories with return visits.
- PHOTO-01: photo capture, metadata, album, and export.

### P1 — Living city

- SCHED-01: resident work, home, leisure, and shelter routines.
- NAV-01: shared walkable paths with cached distance fields.
- WEATHER-01: umbrellas, shelters, wetness, and weather-driven decisions.
- CITYWATCH-01: zero-player simulation with captions, names, roles, and camera focus.
- EVENT-01: staged public events with multiple actors and beats.

### P2 — Atmosphere and depth

- AUDIO-01: continuous environmental layers with location-aware attenuation.
- TRANSIT-01: boat and future tram routes with observation shots.
- VERT-01: bridges, rooftops, underground paths, and limited vertical travel.
- WINDOW-01: employees, customers, steam, closing hours, and moving interiors behind glass.
- SEASON-01: fog mornings, snow, festivals, and seasonal decoration.
- MOD-01: JSON definitions for stores, NPCs, stories, interiors, and events.

## Future ideas

Relationship memory, multi-stage dialogue, a simple economy, photo scoring, rare power cuts and festivals, ghost walks from previous players, optional ambient music backends, a browser preview, and terminal snapshots that are easy to share.

## Definition of done

A feature is ready when it has a deterministic seed path, does not block the terminal loop, has a clear fallback when optional dependencies are missing, includes focused tests where behavior is non-trivial, and has a preview or short reproduction command when it changes visuals.

## Delegating a task

Give a model one task ID, the files it may change, acceptance criteria, and the command it must run. Ask it to report changed files, tests, remaining risks, and a suggested commit message. Keep rendering, simulation, and terminal I/O changes in separate tasks when possible.
