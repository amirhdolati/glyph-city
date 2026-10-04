"""Deterministic selection of nearby, visible interaction targets.

The renderer and input loop can use this module without knowing anything about
the concrete action.  A candidate is data; the caller decides what to do when
its ``action`` is activated.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable, Protocol


class LineOfSight(Protocol):
    def __call__(self, player_x: float, player_y: float,
                 target_x: float, target_y: float) -> bool: ...


@dataclass(frozen=True)
class InteractionCandidate:
    """An action that can be activated when the player is looking at it."""

    id: str
    action: str
    label: str
    x: float
    y: float
    radius: float = 2.0
    facing_angle: float = math.pi / 3
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.id or not self.action or not self.label:
            raise ValueError('interaction id, action and label are required')
        if not all(math.isfinite(v) for v in (self.x, self.y, self.radius, self.facing_angle)):
            raise ValueError('interaction coordinates and ranges must be finite')
        if self.radius <= 0 or not 0 < self.facing_angle <= math.pi:
            raise ValueError('interaction radius and facing angle are invalid')


def _angle_delta(a: float, b: float) -> float:
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def select_candidate(player_x: float, player_y: float, facing: float,
                     candidates: Iterable[InteractionCandidate], *,
                     line_of_sight: LineOfSight | None = None) -> InteractionCandidate | None:
    """Return the best candidate using stable priority/distance/id ordering.

    ``line_of_sight`` receives player and target coordinates.  Omitting it is
    useful for menus and tests; a game world should provide its wall test.
    """
    if not all(math.isfinite(v) for v in (player_x, player_y, facing)):
        raise ValueError('player coordinates and facing must be finite')
    valid: list[tuple[int, float, str, InteractionCandidate]] = []
    for candidate in candidates:
        distance = math.hypot(candidate.x - player_x, candidate.y - player_y)
        if distance > candidate.radius:
            continue
        if distance > 1e-9:
            target_angle = math.atan2(candidate.y - player_y, candidate.x - player_x)
            if abs(_angle_delta(target_angle, facing)) > candidate.facing_angle / 2:
                continue
        if line_of_sight is not None and not line_of_sight(
                player_x, player_y, candidate.x, candidate.y):
            continue
        valid.append((-candidate.priority, distance, candidate.id, candidate))
    if not valid:
        return None
    valid.sort(key=lambda item: item[:3])
    return valid[0][3]


def prompt_for(candidate: InteractionCandidate | None) -> str:
    """Return the compact prompt shown by a terminal HUD."""
    return '' if candidate is None else f'[Enter] {candidate.label}'

