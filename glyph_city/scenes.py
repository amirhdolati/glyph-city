"""Minimal scene/portal contract for the first interior room."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Portal:
    id: str
    from_scene: str
    to_scene: str
    entry: tuple[float, float]
    exit: tuple[float, float]


@dataclass(frozen=True)
class Scene:
    id: str
    width: int
    height: int
    roof: bool = True
    paused_outdoor_clock: bool = False


OUTDOOR = Scene('afterlight', 120, 120, roof=False)
CAFE = Scene('cafe', 18, 12, roof=True)
PORTALS = (Portal('cafe_door', 'afterlight', 'cafe', (69.5, 42.5), (8.0, 10.0)),
           Portal('cafe_exit', 'cafe', 'afterlight', (69.5, 42.5), (69.0, 44.0)))


def portal_for(scene_id: str, x: float, y: float):
    for portal in PORTALS:
        if portal.from_scene == scene_id and abs(x-portal.entry[0]) < 1.5 and abs(y-portal.entry[1]) < 1.5:
            return portal
    return None
