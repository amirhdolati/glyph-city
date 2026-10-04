# Rendering, Gameplay, and Controls Plan

## Input contract

Movement is state-based. Pressing W, A, S, or D changes one held-key state; releasing it removes only that key. Q and E rotate independently from movement. Shift is an independent sprint modifier. A brake action clears movement without changing the camera angle.

Enhanced keyboard protocol terminals provide release events. Legacy terminals use repeat timing and a conservative fallback. Focus loss always clears movement and sprint state.

## Camera and movement

The player uses smoothed acceleration, diagonal normalization, substeps near walls, and separate collision checks for each axis. Camera bob is optional. City Watch uses a read-only camera copy so observation never changes the saved player location. Cinematic shots ease between anchors and may follow a resident during a staged event.

## Renderer plan

The renderer is a dependency-free Python ray caster. It projects variable-height building faces into terminal cells, maintains a depth buffer, samples ground materials, and draws sprites after surfaces. Materials control wetness and reflection strength. Lighting combines time-of-day, local lamp glow, lantern beam, facade emission, and a restrained fog grade.

Transparent ground-floor panes trace a small furnished room behind the glass. The interior layer is deterministic per building and sign, so a cafe, bookshop, hotel, bar, lounge, or mature venue keeps a stable visual identity.

The renderer must preserve readable silhouettes before atmosphere. Fog, reflections, rain, and storm flashes are limited by distance and material so they do not erase doors, NPCs, signs, or windows.

## Living simulation

Residents have names, roles, home and work destinations, activity labels, shelter decisions, dialogue, and social cooldowns. Cached walkable distance fields avoid pathfinding every frame. Public events are staged in beats and update actor activity, dialogue, captions, and camera focus together.

## Weather and sound

Rain changes route decisions, umbrella state, shelter behavior, ground wetness, reflections, and the sound mix. The audio interface must remain safe when no backend is installed. Ambient layers should be continuous and long enough to avoid audible seams; one-shot Foley is spatialized by distance and camera heading.

## Test matrix

- Press and release movement keys in every order.
- Hold W+D, then release only D; forward movement must continue.
- Toggle City Watch while a movement key is held.
- Resize the terminal during rain, storm, map, journal, settings, and photo mode.
- Render clear, dusk, night, rain, storm, mist, and glass interiors at fixed seeds.
- Enter and leave the cafe and boat without changing the outdoor save position.
- Run without NumPy or a native audio backend.
- Run the full suite with `python3 -m unittest discover -s tests -v`.
