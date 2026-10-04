"""Clock-based NPC schedule planning with safe, non-teleporting reloads."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .navigation import NavigationGraph, Route


@dataclass(frozen=True)
class ScheduleSegment:
    start_hour: float
    end_hour: float
    destination: tuple[float, float]
    action: str = 'walk'
    fallback: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.start_hour, self.end_hour,
                                                       *self.destination)):
            raise ValueError('schedule times and coordinates must be finite')
        if not 0 <= self.start_hour < 24 or not 0 <= self.end_hour <= 24:
            raise ValueError('schedule hours must be in [0, 24]')
        if self.start_hour == self.end_hour:
            raise ValueError('schedule segment cannot have an empty time range')
        if not self.action.strip():
            raise ValueError('schedule action is required')
        if self.fallback is not None and not all(math.isfinite(value) for value in self.fallback):
            raise ValueError('schedule fallback coordinates must be finite')

    def contains(self, hour: float) -> bool:
        hour %= 24.0
        if self.end_hour == 24:
            return self.start_hour <= hour < 24
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


@dataclass(frozen=True)
class NPCSchedule:
    id: str
    segments: tuple[ScheduleSegment, ...]
    safe_point: tuple[float, float]

    def __post_init__(self) -> None:
        if not self.id or not self.segments:
            raise ValueError('schedule id and segments are required')
        if not all(math.isfinite(value) for value in self.safe_point):
            raise ValueError('safe point coordinates must be finite')
        ordered = sorted(self.segments, key=lambda item: item.start_hour)
        for left, right in zip(ordered, ordered[1:]):
            if left.end_hour > right.start_hour:
                raise ValueError('schedule segments overlap')

    def at(self, hour: float) -> tuple[int, ScheduleSegment] | None:
        if not math.isfinite(hour):
            raise ValueError('schedule hour must be finite')
        normalized = hour % 24.0
        for index, segment in enumerate(self.segments):
            if segment.contains(normalized):
                return index, segment
        return None


@dataclass(frozen=True)
class SchedulePlan:
    npc_id: str
    segment_index: int | None
    destination: tuple[float, float]
    action: str
    route: Route | None
    used_fallback: bool
    paused: bool = False


class SchedulePlanner:
    """Resolve NPC destinations from game time, without owning NPC movement.

    Recomputing after a time jump or reload starts from the NPC's current
    position and returns a route. It never writes to the actor's coordinates.
    """

    def __init__(self, navigation: NavigationGraph):
        self.navigation = navigation

    def plan(self, city, schedule: NPCSchedule, hour: float,
                  current: tuple[float, float], *, paused: bool = False,
                  previous: SchedulePlan | None = None) -> SchedulePlan:
        if paused and previous is not None:
            return SchedulePlan(previous.npc_id, previous.segment_index,
                                previous.destination, previous.action, previous.route,
                                previous.used_fallback, paused=True)
        selected = schedule.at(hour)
        if selected is None:
            segment_index, segment = None, None
            target, action = schedule.safe_point, 'wait'
        else:
            segment_index, segment = selected
            target, action = segment.destination, segment.action
        route = self.navigation.route(city, current, target,
                                      fallback=(segment.fallback if segment else schedule.safe_point))
        if route is None:
            # No path exists from current position: remain in place if safe,
            # otherwise return a route to the schedule's known safe point.
            target = current if city.walkable(*current) else schedule.safe_point
            route = self.navigation.route(city, current, target, fallback=schedule.safe_point)
            action = 'wait'
        return SchedulePlan(schedule.id, segment_index, target, action, route,
                            route.used_fallback if route else True)

    # Explicit alias makes call sites read naturally when they emphasize the
    # city validation step.
    plan_city = plan


def default_schedules() -> tuple[NPCSchedule, ...]:
    """Two sample routines with distinct morning/evening behavior."""
    vendor = NPCSchedule('tea_vendor', (
        ScheduleSegment(6, 12, (72.5, 48.5), 'open_shop', (60.5, 89.5)),
        ScheduleSegment(12, 19, (68.5, 48.5), 'serve', (60.5, 89.5)),
        ScheduleSegment(19, 6, (60.5, 89.5), 'close_shop', (72.5, 48.5)),
    ), safe_point=(60.5, 89.5))
    walker = NPCSchedule('canal_walker', (
        ScheduleSegment(5, 11, (48.5, 60.5), 'walk', (60.5, 89.5)),
        ScheduleSegment(11, 17, (60.5, 89.5), 'rest', (48.5, 60.5)),
        ScheduleSegment(17, 23, (84.5, 36.5), 'walk', (60.5, 89.5)),
        ScheduleSegment(23, 5, (60.5, 89.5), 'return_home', (84.5, 36.5)),
    ), safe_point=(60.5, 89.5))
    return vendor, walker
