"""Shelter and umbrella exposure queries for the authored city.

This module reports gameplay exposure only. Rendering and world-state updates
remain owned by their callers, so the query is deterministic and side-effect free.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class Shelter:
    id: str
    x0: float
    y0: float
    x1: float
    y1: float
    coverage: float = 1.0

    def __post_init__(self) -> None:
        if not self.id or not all(math.isfinite(value) for value in
                                  (self.x0, self.y0, self.x1, self.y1, self.coverage)):
            raise ValueError('shelter fields must be finite and id must be set')
        if self.x1 < self.x0 or self.y1 < self.y0 or not 0 <= self.coverage <= 1:
            raise ValueError('shelter bounds or coverage are invalid')

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


@dataclass(frozen=True)
class UmbrellaState:
    open: bool = False
    coverage: float = .72

    def __post_init__(self) -> None:
        if not math.isfinite(self.coverage) or not 0 <= self.coverage <= 1:
            raise ValueError('umbrella coverage must be between 0 and 1')

    def toggled(self) -> 'UmbrellaState':
        return UmbrellaState(not self.open, self.coverage)


@dataclass(frozen=True)
class WeatherExposure:
    ambient: float
    shelter_coverage: float
    umbrella_coverage: float
    intensity: float
    shelter_id: str | None
    protected: bool


class ShelterMap:
    """Ordered, stable shelter lookup and local rain intensity calculation."""

    def __init__(self, shelters: Iterable[Shelter] = ()):
        self.shelters = tuple(sorted(shelters, key=lambda item: item.id))
        ids = [item.id for item in self.shelters]
        if len(ids) != len(set(ids)):
            raise ValueError('shelter ids must be unique')

    def at(self, x: float, y: float) -> Shelter | None:
        _coordinates(x, y)
        candidates = [shelter for shelter in self.shelters if shelter.contains(x, y)]
        return max(candidates, key=lambda item: (item.coverage, item.id), default=None)

    def exposure(self, x: float, y: float, rain_intensity: float, *,
                 umbrella: UmbrellaState | None = None) -> WeatherExposure:
        _coordinates(x, y)
        if not math.isfinite(rain_intensity):
            raise ValueError('rain intensity must be finite')
        ambient = min(1.0, max(0.0, rain_intensity))
        shelter = self.at(x, y)
        shelter_cover = shelter.coverage if shelter else 0.0
        umbrella_cover = umbrella.coverage if umbrella is not None and umbrella.open else 0.0
        # Independent partial cover combines without producing negative rain.
        uncovered = (1.0 - shelter_cover) * (1.0 - umbrella_cover)
        intensity = ambient * uncovered
        return WeatherExposure(ambient, shelter_cover, umbrella_cover, intensity,
                               shelter.id if shelter else None,
                               ambient > 0 and intensity <= ambient * .3)


def default_shelters() -> ShelterMap:
    """Bridge roofs and market awnings, deliberately small authored volumes."""
    return ShelterMap((
        Shelter('canal_bridge', 55.5, 88.5, 65.5, 94.5, .92),
        Shelter('market_awning', 64.5, 46.5, 77.5, 50.5, .82),
        Shelter('market_entry', 69.5, 40.5, 74.5, 43.5, .68),
    ))


def _coordinates(x: float, y: float) -> None:
    if not all(math.isfinite(value) for value in (x, y)):
        raise ValueError('coordinates must be finite')

