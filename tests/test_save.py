import json
from pathlib import Path
import tempfile
import unittest

from glyph_city.game import make_world
from glyph_city.save import (AutosaveController, SaveNotFoundError, SaveSchemaError,
                             SaveStore, load_world, save_world)


class SaveStorageChecks(unittest.TestCase):
    def test_round_trip_and_previous_is_previous_valid_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'save.json'
            store = SaveStore(path)
            first = make_world(seed=7, hour=8, weather='clear')
            store.save_world(first)
            first_bytes = path.read_bytes()
            second = make_world(seed=9, hour=21, weather='rain')
            store.save_world(second)
            self.assertEqual(store.backup_path.read_bytes(), first_bytes)
            loaded = store.load_world()
            self.assertEqual(loaded.city.seed, 9)
            self.assertEqual(loaded.weather, 1)

    def test_corrupt_primary_recovers_from_previous_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'save.json'
            store = SaveStore(path)
            store.save_world(make_world(seed=11))
            store.save_world(make_world(seed=12))
            path.write_bytes(b'{"schema_version":')
            loaded = store.load_world()
            self.assertEqual(loaded.city.seed, 11)
            self.assertEqual(path.read_bytes(), b'{"schema_version":')

    def test_save_overwrites_corrupt_primary_without_poisoning_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'save.json'
            store = SaveStore(path)
            store.save_world(make_world(seed=21))
            store.save_world(make_world(seed=22))
            backup = store.backup_path.read_bytes()
            path.write_text('broken', encoding='utf-8')
            store.save_world(make_world(seed=23))
            self.assertEqual(store.backup_path.read_bytes(), backup)
            self.assertEqual(store.load_world().city.seed, 23)

    def test_missing_and_invalid_files_have_clear_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'save.json'
            with self.assertRaises(SaveNotFoundError):
                load_world(path)
            path.write_text(json.dumps({'schema_version': 999}), encoding='utf-8')
            with self.assertRaises(SaveSchemaError):
                load_world(path)

    def test_convenience_functions_accept_injected_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'nested' / 'save.json'
            world = make_world(seed=31, hour=4, weather='mist')
            self.assertEqual(save_world(world, path), path)
            self.assertEqual(load_world(path).city.seed, 31)

    def test_autosave_is_debounced_and_flushes_on_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            now = [100.0]
            store = SaveStore(Path(folder) / 'save.json')
            controller = AutosaveController(store, interval=30, clock=lambda: now[0])
            first = make_world(seed=41)
            self.assertTrue(controller.request(first, 'discovery'))
            second = make_world(seed=42)
            now[0] = 110
            self.assertFalse(controller.request(second, 'story'))
            self.assertTrue(controller.pending)
            now[0] = 131
            self.assertTrue(controller.maybe_save())
            self.assertEqual(store.load_world().city.seed, 42)
            third = make_world(seed=43)
            now[0] = 132
            controller.request(third, 'exit')
            self.assertTrue(controller.save_on_exit())
            self.assertEqual(store.load_world().city.seed, 43)

    def test_autosave_does_not_write_without_a_progress_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'save.json'
            controller = AutosaveController(SaveStore(path), interval=0, clock=lambda: 1)
            self.assertFalse(controller.maybe_save())
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
