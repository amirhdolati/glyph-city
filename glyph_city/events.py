"""Deterministic, optional neighborhood events.

Events are data-only so the terminal loop can present them without coupling the
story save format to rendering or audio.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NeighborhoodEvent:
    id: str
    title: str
    text: str
    start_hour: float
    end_hour: float
    fallback: str = ''
    target: tuple[float, float] = (60.0, 60.0)

    def active(self, hour: float) -> bool:
        hour %= 24
        return self.start_hour <= hour < self.end_hour


DEFAULT_EVENTS = (
    NeighborhoodEvent('evening_lamps', 'Lantern lighting',
                      'The market lamps wake one by one.', 18, 22,
                      'The market is quiet; return after sunset.', (72.0, 48.0)),
    NeighborhoodEvent('canal_musician', 'Canal musician',
                      'A distant melody follows the rain along the canal.', 19, 23,
                      'Only the canal bells answer tonight.', (60.0, 85.0)),
)


def available_events(hour: float, completed=(), events=DEFAULT_EVENTS):
    done=set(completed)
    return tuple(event for event in events if event.id not in done and event.active(hour))
