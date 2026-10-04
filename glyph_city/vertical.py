"""A bounded elevation experiment; the main city remains flat."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ElevationSample:
    x: float
    y: float
    z: float


ROOFTOP_SAMPLE=(ElevationSample(84.5,36.5,0.0),ElevationSample(84.5,36.5,2.0))


def elevation_at(x: float, y: float) -> float:
    return 2.0 if 83 <= x <= 86 and 35 <= y <= 38 else 0.0
