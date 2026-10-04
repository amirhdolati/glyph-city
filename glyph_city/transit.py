"""One authored canal boat route with explicit boarding state."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TransitStop:
    id: str
    x: float
    y: float


STOPS=(TransitStop('canal_north',60.0,85.0),TransitStop('canal_south',60.0,96.0))


@dataclass
class BoatRide:
    riding: bool = False
    progress: float = 0.0
    origin: str | None = None

    def board(self, stop_id: str) -> bool:
        if stop_id not in {stop.id for stop in STOPS}: return False
        self.riding=True; self.origin=stop_id; self.progress=0.0; return True

    def update(self, dt: float) -> None:
        if self.riding: self.progress=min(1.0,self.progress+max(0.0,dt)/18.0)

    def disembark(self) -> str | None:
        if not self.riding: return None
        destination='canal_south' if self.origin=='canal_north' else 'canal_north'
        self.riding=False; self.origin=None; self.progress=0.0
        return destination
