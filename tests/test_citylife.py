import unittest

from glyph_city.city import City
from glyph_city.navigation import NavigationGraph
from glyph_city.schedules import SchedulePlanner, default_schedules
from glyph_city.weather import UmbrellaState, default_shelters


class NavigationChecks(unittest.TestCase):
    def setUp(self):
        self.city = City(17)
        self.graph = NavigationGraph(self.city)

    def test_authored_market_to_canal_route_is_deterministic_and_walkable(self):
        route = self.graph.route(self.city, (72.5, 48.5), (60.5, 89.5))
        again = self.graph.route(self.city, (72.5, 48.5), (60.5, 89.5))
        self.assertIsNotNone(route)
        self.assertEqual(route, again)
        self.assertFalse(route.used_fallback)
        self.assertEqual(route.points[-1], (60.5, 89.5))
        self.assertTrue(all(self.city.walkable(*point) for point in route.points))

    def test_removed_destination_uses_safe_stop(self):
        route = self.graph.route(self.city, (60.5, 78.5), (48.5, 48.5))
        self.assertIsNotNone(route)
        self.assertTrue(route.used_fallback)
        self.assertIn(route.destination_id, self.graph.safe_stops)


class ScheduleChecks(unittest.TestCase):
    def test_midnight_segment_and_pause_are_stable(self):
        city = City(17)
        planner = SchedulePlanner(NavigationGraph(city))
        schedule = default_schedules()[0]
        morning = planner.plan(city, schedule, 7.0, (60.5, 89.5))
        late = planner.plan(city, schedule, 23.0, (60.5, 89.5))
        self.assertEqual(morning.action, 'open_shop')
        self.assertEqual(late.action, 'close_shop')
        paused = planner.plan(city, schedule, 12.0, (60.5, 89.5),
                              paused=True, previous=late)
        self.assertEqual(paused, late.__class__(late.npc_id, late.segment_index,
                                                late.destination, late.action,
                                                late.route, late.used_fallback, True))


class WeatherChecks(unittest.TestCase):
    def test_shelter_and_umbrella_combine_without_zeroing_ambient_weather(self):
        shelters = default_shelters()
        exposed = shelters.exposure(40, 40, 1.0)
        covered = shelters.exposure(60, 90, 1.0)
        umbrella = shelters.exposure(40, 40, 1.0, umbrella=UmbrellaState(True))
        self.assertEqual(exposed.intensity, 1.0)
        self.assertLess(covered.intensity, exposed.intensity)
        self.assertLess(umbrella.intensity, exposed.intensity)
        self.assertEqual(covered.shelter_id, 'canal_bridge')


if __name__ == '__main__':
    unittest.main()
