import math
import unittest

from glyph_city.interactions import InteractionCandidate, prompt_for, select_candidate
from glyph_city.journal import BookStory, Journal, JournalEntry


class InteractionChecks(unittest.TestCase):
    def test_selection_uses_facing_los_priority_distance_and_stable_id(self):
        candidates = [
            InteractionCandidate('far', 'read', 'Far', 1.5, 0, radius=2.0),
            InteractionCandidate('near', 'read', 'Near', 1.0, 0, radius=2.0),
            InteractionCandidate('behind', 'read', 'Behind', -1, 0, radius=2.0),
            InteractionCandidate('blocked', 'read', 'Blocked', .5, .1, radius=2.0,
                                 priority=5),
        ]
        target = select_candidate(0, 0, 0, candidates,
                                  line_of_sight=lambda px, py, tx, ty: tx != .5)
        self.assertEqual(target.id, 'near')
        self.assertEqual(prompt_for(target), '[Enter] Near')
        self.assertIsNone(select_candidate(0, 0, math.pi / 2, candidates))

    def test_equal_candidates_are_deterministic_by_id(self):
        a = InteractionCandidate('b', 'x', 'B', 1, 0)
        b = InteractionCandidate('a', 'x', 'A', 1, 0)
        self.assertEqual(select_candidate(0, 0, 0, (a, b)).id, 'a')


class JournalChecks(unittest.TestCase):
    def test_entries_are_unique_and_status_only_advances(self):
        journal = Journal()
        journal.record('park', kind='landmark', title='Park', target=(1, 2))
        journal.record('park', kind='landmark', title='Park', status='complete')
        journal.mark_seen('park')
        self.assertEqual(len(journal.entries()), 1)
        self.assertEqual(journal.get('park').status, 'complete')
        self.assertEqual(journal.destination('park'), (1, 2))
        restored = Journal.from_dict(journal.to_dict())
        self.assertEqual(restored.to_dict(), journal.to_dict())


class BookStoryChecks(unittest.TestCase):
    def test_three_steps_progress_in_order(self):
        flags = set()
        self.assertEqual(BookStory.current_step(flags).flag, 'book_found')
        BookStory.complete(flags, 'book')
        self.assertEqual(BookStory.current_step(flags).flag, 'seller_hint')
        BookStory.complete(flags, 'seller')
        self.assertEqual(BookStory.current_step(flags).flag, 'postcard_received')
        BookStory.complete(flags, 'postcard')
        self.assertIsNone(BookStory.current_step(flags))

    def test_time_window_has_fallback_and_candidates_are_promptable(self):
        flags = {'book_found'}
        name, target = BookStory.destination(BookStory.steps[1], 10)
        self.assertEqual((name, target), ('Moonwater Canal', (60.0, 85.0)))
        name, target = BookStory.destination(BookStory.steps[1], 18)
        self.assertEqual((name, target), ('Lantern Market', (72.0, 48.0)))
        candidate = BookStory.candidates(flags, 10)[0]
        self.assertEqual(candidate.priority, 100)


if __name__ == '__main__':
    unittest.main()
