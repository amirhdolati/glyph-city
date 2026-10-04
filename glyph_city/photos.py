"""Persistent terminal photographs, stored separately from the game save."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .city import WEATHER


@dataclass(frozen=True)
class Photograph:
    id: str
    district: str
    hour: float
    weather: str
    seed: int
    captured_at: str
    html_path: str
    ansi_path: str

    def to_dict(self) -> dict:
        return vars(self).copy()


class PhotoAlbum:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def capture(self, world, cells, *, export_html, encode_ansi,
                aspect: float, truecolor: bool) -> Photograph:
        """Store a HUD-free frame and its metadata using a unique safe name."""
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc)
        photo_id = stamp.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:12]
        html_name, ansi_name = photo_id + '.html', photo_id + '.ans'
        photo = Photograph(photo_id, world.city.district(world.x, world.y),
                           round(world.clock, 4), WEATHER[world.weather].lower(),
                           world.city.seed, stamp.isoformat(), html_name, ansi_name)
        html_path = self.directory / html_name
        ansi_path = self.directory / ansi_name
        metadata_path = self.directory / (photo_id + '.json')
        try:
            export_html(cells, html_path, aspect)
            ansi_path.write_text(encode_ansi(cells, truecolor), encoding='utf-8')
            metadata_path.write_text(json.dumps(photo.to_dict(), sort_keys=True) + '\n',
                                     encoding='utf-8')
        except OSError:
            for path in (html_path, ansi_path, metadata_path):
                path.unlink(missing_ok=True)
            raise
        return photo

    def entries(self) -> tuple[Photograph, ...]:
        """Read completed captures; ignore invalid or interrupted sidecars."""
        if not self.directory.is_dir():
            return ()
        entries = []
        for metadata_path in self.directory.glob('*.json'):
            try:
                raw = json.loads(metadata_path.read_text(encoding='utf-8'))
                photo = Photograph(**raw)
                if (metadata_path.stem != photo.id or '/' in photo.id or '\\' in photo.id
                        or photo.html_path != photo.id + '.html'
                        or photo.ansi_path != photo.id + '.ans'
                        or not (self.directory / photo.html_path).is_file()
                        or not (self.directory / photo.ansi_path).is_file()):
                    continue
                entries.append(photo)
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return tuple(sorted(entries, key=lambda entry: entry.id, reverse=True))
