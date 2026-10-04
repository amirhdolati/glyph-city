"""Versioned, deterministic save data for Glyph City.

The save contract contains player progress and world choices only.  Motion
velocity, animation timers, weather interpolation and UI toasts are runtime
cache and are deliberately rebuilt when a save is loaded.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Mapping

from .city import City, WEATHER, World

SCHEMA_VERSION = 1
GENERATOR_VERSION = 'afterlight-1'
DEFAULT_SCENE_ID = 'afterlight'

# These IDs are part of the file format.  Their order must follow the current
# landmark list, but the saved representation is always a sorted string list.
LANDMARK_IDS = (
    'willow_gardens',
    'lantern_market',
    'copper_lane',
    'moonwater_canal',
    'glass_quarter',
    'afterlight_crossing',
)


class SaveSchemaError(ValueError):
    """Raised when a save is not compatible with the supported schema."""


class SaveFileError(OSError):
    """Raised when a save cannot be read or written on the filesystem."""


class SaveNotFoundError(SaveFileError):
    """Raised when neither the primary save nor its backup exists."""


class AutosaveController:
    """Throttle progress saves and provide explicit shutdown saving.

    Gameplay calls :meth:`request` only for meaningful progress events such as
    landmark discovery or a story flag change.  :meth:`maybe_save` can then be
    called from the loop without writing every frame.  ``clock`` is injected
    so the debounce policy can be tested without sleeping.
    """

    def __init__(self, store: 'SaveStore', *, interval: float = 30.0,
                 clock: Callable[[], float] | None = None):
        if not math.isfinite(interval) or interval < 0:
            raise ValueError('autosave interval must be a finite non-negative number')
        self.store = store
        self.interval = float(interval)
        self.clock = clock or time.monotonic
        self._last_save: float | None = None
        self._pending: World | None = None
        self.last_reason: str | None = None

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def request(self, world: World, reason: str = 'progress') -> bool:
        """Queue the latest world for a throttled save."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('autosave reason must be a non-empty string')
        self._pending = world
        self.last_reason = reason.strip()
        return self.maybe_save()

    def maybe_save(self, *, now: float | None = None) -> bool:
        """Save a pending snapshot when the debounce interval has elapsed."""
        if self._pending is None:
            return False
        timestamp = self.clock() if now is None else float(now)
        if not math.isfinite(timestamp):
            raise ValueError('autosave clock must return a finite number')
        if self._last_save is not None and timestamp - self._last_save < self.interval:
            return False
        world = self._pending
        self.store.save_world(world)
        self._pending = None
        self._last_save = timestamp
        return True

    def save_on_exit(self, world: World | None = None, *, now: float | None = None) -> bool:
        """Flush the latest pending world during a normal shutdown."""
        if world is not None:
            self._pending = world
        if self._pending is None:
            return False
        timestamp = self.clock() if now is None else float(now)
        if not math.isfinite(timestamp):
            raise ValueError('autosave clock must return a finite number')
        self.store.save_world(self._pending)
        self._pending = None
        self._last_save = timestamp
        return True


class SaveStore:
    """Filesystem storage for one save slot.

    ``path`` is injectable so callers and tests can choose the exact location.
    Writes use a temporary file in the destination directory followed by
    ``os.replace``.  A valid previous primary is copied to ``.previous``
    before the new payload replaces it.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None, *, backup_path=None):
        self.path = Path(path) if path is not None else default_save_path()
        self.backup_path = (Path(backup_path) if backup_path is not None else
                            self.path.with_name(self.path.name + '.previous'))

    def save_world(self, world: World) -> Path:
        """Atomically write ``world`` and retain the last valid primary."""
        payload = dumps(world).encode('utf-8')
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            previous = self._read_valid(self.path)
            if previous is not None:
                self._atomic_write(self.backup_path, previous)
            self._atomic_write(self.path, payload)
        except SaveSchemaError:
            # The new payload was produced from a valid World; this branch is
            # reserved for a future serializer that can reject it.
            raise
        except (OSError, ValueError) as exc:
            raise SaveFileError(f'could not save game to {self.path}: {exc}') from exc
        return self.path

    def load_world(self, *, city_factory=City, recover=True) -> World:
        """Load the primary save, falling back to a valid ``.previous`` file.

        A malformed primary is never copied into the backup.  If both files
        are present but invalid, the primary schema error is re-raised so the
        caller can show a useful diagnostic.
        """
        primary_error = None
        try:
            data = self.path.read_bytes()
        except FileNotFoundError as exc:
            primary_error = SaveNotFoundError(f'save file does not exist: {self.path}')
        except OSError as exc:
            primary_error = SaveFileError(f'could not read save {self.path}: {exc}')
        else:
            try:
                return loads(data, city_factory=city_factory)
            except SaveSchemaError as exc:
                primary_error = exc

        backup_error = None
        if recover:
            try:
                data = self.backup_path.read_bytes()
            except FileNotFoundError:
                pass
            except OSError as exc:
                if primary_error is None:
                    raise SaveFileError(f'could not read backup save {self.backup_path}: {exc}') from exc
            else:
                try:
                    return loads(data, city_factory=city_factory)
                except SaveSchemaError as exc:
                    backup_error = exc
        if isinstance(primary_error, SaveNotFoundError) and backup_error is not None:
            raise backup_error
        if primary_error is not None:
            raise primary_error
        raise SaveNotFoundError(f'no save found at {self.path} or {self.backup_path}')

    def _read_valid(self, path: Path) -> bytes | None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        # Validation prevents a malformed primary from becoming the recovery
        # copy.  Preserve the original bytes so backup is byte stable.
        try:
            loads(data)
        except SaveSchemaError:
            return None
        return data

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp',
                                         dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def default_save_path() -> Path:
    """Return the platform data path without depending on the repository."""
    home = Path.home()
    if os.name == 'nt':
        root = Path(os.environ.get('APPDATA', home / 'AppData' / 'Roaming'))
        return root / 'GlyphCity' / 'save.json'
    if sys_platform() == 'darwin':
        return home / 'Library' / 'Application Support' / 'Glyph City' / 'save.json'
    root = Path(os.environ.get('XDG_DATA_HOME', home / '.local' / 'share'))
    return root / 'glyph-city' / 'save.json'


def sys_platform() -> str:
    """Small seam for platform-path tests without mocking ``os.name``."""
    import sys
    return sys.platform


def save_world(world: World, path=None, *, backup_path=None) -> Path:
    """Convenience wrapper around :class:`SaveStore`."""
    return SaveStore(path, backup_path=backup_path).save_world(world)


def load_world(path=None, *, backup_path=None, city_factory=City, recover=True) -> World:
    """Convenience wrapper around :class:`SaveStore`."""
    return SaveStore(path, backup_path=backup_path).load_world(city_factory=city_factory,
                                                               recover=recover)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SaveSchemaError(f'{name} must be an object')
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SaveSchemaError(f'{name} must be a number')
    value = float(value)
    if not math.isfinite(value):
        raise SaveSchemaError(f'{name} must be finite')
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list):
        raise SaveSchemaError(f'{name} must be an array')
    if any(not isinstance(item, str) or not item for item in value):
        raise SaveSchemaError(f'{name} must contain non-empty strings')
    if len(set(value)) != len(value):
        raise SaveSchemaError(f'{name} must not contain duplicates')
    return sorted(value)


def _landmark_id(index: Any) -> str:
    if isinstance(index, bool) or not isinstance(index, int):
        if isinstance(index, str) and index in LANDMARK_IDS:
            return index
        raise SaveSchemaError(f'visited_landmarks contains an unknown ID: {index!r}')
    if not 0 <= index < len(LANDMARK_IDS):
        raise SaveSchemaError(f'visited landmark index is out of range: {index!r}')
    return LANDMARK_IDS[index]


def world_to_dict(world: World) -> dict[str, Any]:
    """Return the canonical save object for ``world``.

    Canonical arrays are sorted, and callers should serialize the returned
    object with :func:`dumps` when byte-for-byte deterministic output matters.
    """
    visited = sorted({_landmark_id(item) for item in world.visited})
    flags = sorted(set(getattr(world, 'story_flags', set())))
    if any(not isinstance(flag, str) or not flag for flag in flags):
        raise SaveSchemaError('story_flags must contain non-empty strings')
    events = sorted(set(getattr(world, 'event_flags', set())))
    if any(not isinstance(event, str) or not event for event in events):
        raise SaveSchemaError('event_flags must contain non-empty strings')
    scene_id = getattr(world, 'scene_id', DEFAULT_SCENE_ID)
    if not isinstance(scene_id, str) or not scene_id:
        raise SaveSchemaError('scene_id must be a non-empty string')
    if not isinstance(world.city.seed, int) or isinstance(world.city.seed, bool):
        raise SaveSchemaError('city seed must be an integer')
    weather = int(world.weather)
    if weather < 0 or weather >= len(WEATHER):
        raise SaveSchemaError(f'weather index is out of range: {weather!r}')
    return {
        'schema_version': SCHEMA_VERSION,
        'generator_version': GENERATOR_VERSION,
        'seed': world.city.seed,
        'position': {'x': _number(world.x, 'position.x'), 'y': _number(world.y, 'position.y')},
        'orientation': {'angle': _number(world.angle, 'orientation.angle'),
                        'pitch': _number(world.pitch, 'orientation.pitch')},
        'clock': {'hour': _number(world.clock, 'clock.hour'),
                  'running': bool(world.clock_running)},
        'weather': WEATHER[weather].lower(),
        'visited_landmarks': visited,
        'story_flags': flags,
        'event_flags': events,
        'scene_id': scene_id,
    }


def dumps(world: World) -> str:
    """Serialize ``world`` as stable UTF-8 JSON with no runtime cache."""
    return json.dumps(world_to_dict(world), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def loads(data: str | bytes | bytearray | Mapping[str, Any], *, city_factory=City) -> World:
    """Load a save, ignoring unknown fields for forward compatibility.

    ``city_factory`` is injectable for tests and must accept the saved seed.
    ``SaveSchemaError`` describes malformed or unsupported save data.
    """
    if isinstance(data, Mapping):
        raw = dict(data)
    else:
        try:
            raw = json.loads(data)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise SaveSchemaError(f'invalid JSON save: {exc}') from exc
    root = _mapping(raw, 'save')
    version = root.get('schema_version')
    if version != SCHEMA_VERSION:
        raise SaveSchemaError(f'unsupported schema_version: {version!r}')
    seed = root.get('seed')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SaveSchemaError('seed must be an integer')
    position = _mapping(root.get('position'), 'position')
    orientation = _mapping(root.get('orientation'), 'orientation')
    clock = _mapping(root.get('clock'), 'clock')
    x, y = _number(position.get('x'), 'position.x'), _number(position.get('y'), 'position.y')
    angle = _number(orientation.get('angle'), 'orientation.angle')
    pitch = _number(orientation.get('pitch'), 'orientation.pitch')
    hour = _number(clock.get('hour'), 'clock.hour')
    if not 0 <= hour <= 24:
        raise SaveSchemaError('clock.hour must be between 0 and 24')
    running = clock.get('running')
    if not isinstance(running, bool):
        raise SaveSchemaError('clock.running must be a boolean')
    weather_name = root.get('weather')
    if not isinstance(weather_name, str) or weather_name.upper() not in WEATHER:
        raise SaveSchemaError(f'unknown weather: {weather_name!r}')
    visited = _string_list(root.get('visited_landmarks'), 'visited_landmarks')
    unknown = [item for item in visited if item not in LANDMARK_IDS]
    if unknown:
        raise SaveSchemaError(f'visited_landmarks contains an unknown ID: {unknown[0]!r}')
    flags = _string_list(root.get('story_flags'), 'story_flags')
    events = _string_list(root.get('event_flags', []), 'event_flags')
    scene_id = root.get('scene_id')
    if not isinstance(scene_id, str) or not scene_id:
        raise SaveSchemaError('scene_id must be a non-empty string')
    city = city_factory(seed)
    world = World(city, x=x, y=y, angle=angle, pitch=pitch, clock=hour,
                  weather=WEATHER.index(weather_name.upper()), clock_running=running,
                  visited={LANDMARK_IDS.index(item) for item in visited},
                  story_flags=set(flags), scene_id=scene_id)
    world.event_flags=set(events)
    return world
