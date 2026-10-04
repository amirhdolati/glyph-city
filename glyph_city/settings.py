"""Versioned user preferences for Glyph City.

Settings are deliberately separate from the world save.  A broken preference
file falls back to safe defaults per field so a cosmetic option cannot prevent
the player from continuing a walk.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

SCHEMA_VERSION = 1


class SettingsSchemaError(ValueError):
    """Raised when a settings object has an unsupported shape or version."""


@dataclass(frozen=True)
class Settings:
    palette: str = 'auto'
    truecolor: bool = True
    max_width: int = 160
    fps: int = 24
    aspect: float = 0.5
    mouse_sensitivity: float = 0.018
    camera_bob: bool = True
    night_contrast: float = 1.0
    storm_flash: bool = True
    volume: float = 1.0


DEFAULTS = Settings()
PALETTES = frozenset({'auto', '256', 'truecolor'})


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsSchemaError(f'{name} must be a number')
    value = float(value)
    if not math.isfinite(value):
        raise SettingsSchemaError(f'{name} must be finite')
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsSchemaError(f'{name} must be a boolean')
    return value


def validate(settings: Settings) -> Settings:
    """Validate and normalize a settings instance."""
    if settings.palette not in PALETTES:
        raise SettingsSchemaError('palette must be auto, 256, or truecolor')
    if not isinstance(settings.truecolor, bool):
        raise SettingsSchemaError('truecolor must be a boolean')
    if isinstance(settings.max_width, bool) or not isinstance(settings.max_width, int):
        raise SettingsSchemaError('max_width must be an integer')
    if not 40 <= settings.max_width <= 240:
        raise SettingsSchemaError('max_width must be between 40 and 240')
    if isinstance(settings.fps, bool) or not isinstance(settings.fps, int):
        raise SettingsSchemaError('fps must be an integer')
    if not 5 <= settings.fps <= 60:
        raise SettingsSchemaError('fps must be between 5 and 60')
    aspect = _finite_number(settings.aspect, 'aspect')
    sensitivity = _finite_number(settings.mouse_sensitivity, 'mouse_sensitivity')
    contrast = _finite_number(settings.night_contrast, 'night_contrast')
    volume = _finite_number(settings.volume, 'volume')
    if not .25 <= aspect <= 1:
        raise SettingsSchemaError('aspect must be between 0.25 and 1')
    if not .004 <= sensitivity <= .06:
        raise SettingsSchemaError('mouse_sensitivity must be between 0.004 and 0.06')
    if not .5 <= contrast <= 2:
        raise SettingsSchemaError('night_contrast must be between 0.5 and 2')
    if not 0 <= volume <= 1:
        raise SettingsSchemaError('volume must be between 0 and 1')
    _bool(settings.camera_bob, 'camera_bob')
    _bool(settings.storm_flash, 'storm_flash')
    return replace(settings, aspect=aspect, mouse_sensitivity=sensitivity,
                   night_contrast=contrast, volume=volume)


def to_dict(settings: Settings) -> dict[str, Any]:
    settings = validate(settings)
    return {'schema_version': SCHEMA_VERSION, **{
        field.name: getattr(settings, field.name) for field in fields(Settings)
    }}


def from_mapping(value: Mapping[str, Any]) -> Settings:
    if not isinstance(value, Mapping):
        raise SettingsSchemaError('settings must be an object')
    if value.get('schema_version') != SCHEMA_VERSION:
        raise SettingsSchemaError(f"unsupported schema_version: {value.get('schema_version')!r}")
    values = {field.name: value.get(field.name, getattr(DEFAULTS, field.name))
              for field in fields(Settings)}
    # A malformed individual value is intentionally reset to its default.
    for field in fields(Settings):
        try:
            candidate = replace(DEFAULTS, **{field.name: values[field.name]})
            values[field.name] = getattr(validate(candidate), field.name)
        except SettingsSchemaError:
            values[field.name] = getattr(DEFAULTS, field.name)
    return validate(Settings(**values))


def dumps(settings: Settings) -> str:
    return json.dumps(to_dict(settings), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def loads(data: str | bytes | bytearray | Mapping[str, Any]) -> Settings:
    if isinstance(data, Mapping):
        raw = data
    else:
        try:
            raw = json.loads(data)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise SettingsSchemaError(f'invalid JSON settings: {exc}') from exc
    return from_mapping(raw)


def default_settings_path() -> Path:
    home = Path.home()
    if os.name == 'nt':
        root = Path(os.environ.get('APPDATA', home / 'AppData' / 'Roaming'))
        return root / 'GlyphCity' / 'settings.json'
    import sys
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'Glyph City' / 'settings.json'
    root = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    return root / 'glyph-city' / 'settings.json'


class SettingsStore:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else default_settings_path()

    def load(self) -> Settings:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return DEFAULTS
        except OSError:
            return DEFAULTS
        try:
            return loads(data)
        except SettingsSchemaError:
            return DEFAULTS

    def save(self, settings: Settings) -> Path:
        payload = (dumps(settings) + '\n').encode('utf-8')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f'.{self.path.name}.', suffix='.tmp',
                                         dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return self.path

