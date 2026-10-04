import json
from pathlib import Path
import tempfile
import unittest

from glyph_city.settings import (DEFAULTS, SCHEMA_VERSION, Settings, SettingsStore,
                                 dumps, loads)
from glyph_city.game import adjust_setting


class SettingsChecks(unittest.TestCase):
    def test_in_game_left_right_adjusts_numeric_values(self):
        self.assertEqual(adjust_setting(DEFAULTS, 2, 1).fps, 29)
        self.assertEqual(adjust_setting(DEFAULTS, 2, -1).fps, 19)
        self.assertEqual(adjust_setting(DEFAULTS, 9, -1).volume, .9)
        self.assertFalse(adjust_setting(DEFAULTS, 6, 1).camera_bob)

    def test_round_trip_is_versioned_and_deterministic(self):
        settings = Settings(palette='256', truecolor=False, fps=30,
                            mouse_sensitivity=.024, volume=.4)
        encoded = dumps(settings)
        self.assertEqual(encoded, dumps(loads(encoded)))
        self.assertEqual(json.loads(encoded)['schema_version'], SCHEMA_VERSION)

    def test_invalid_individual_values_fall_back_to_defaults(self):
        raw = {'schema_version': SCHEMA_VERSION, 'fps': 999,
               'max_width': 100, 'night_contrast': 'bright', 'volume': .25}
        settings = loads(raw)
        self.assertEqual(settings.fps, DEFAULTS.fps)
        self.assertEqual(settings.max_width, 100)
        self.assertEqual(settings.night_contrast, DEFAULTS.night_contrast)
        self.assertEqual(settings.volume, .25)

    def test_store_keeps_preferences_separate_and_recovers_bad_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            store = SettingsStore(path)
            chosen = Settings(max_width=120, camera_bob=False, storm_flash=False)
            store.save(chosen)
            self.assertEqual(store.load(), chosen)
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(store.load(), DEFAULTS)

    def test_missing_settings_use_platform_independent_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(SettingsStore(Path(folder) / 'none.json').load(), DEFAULTS)


if __name__ == '__main__':
    unittest.main()
