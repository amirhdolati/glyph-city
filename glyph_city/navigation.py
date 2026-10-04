"""Small deterministic pedestrian graph for the authored Afterlight routes.

The graph is intentionally sparse and manually authored. Edges are checked
against the current City at construction time, so a changed or obstructed map
cannot create a route through a wall or water. The module does not move actors.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Iterable


@dataclass(frozen=True)
class RouteNode:
    id: str
    x: float
    y: float
    kind: str = 'sidewalk'  # sidewalk, bridge, or stop


@dataclass(frozen=True)
class Route:
    points: tuple[tuple[float, float], ...]
    node_ids: tuple[str, ...]
    destination_id: str | None
    used_fallback: bool = False


# Main pedestrian promenade, market approach, and the canal crossing. These
# are authored coordinates, not generated per-NPC navigation meshes.
_DEFAULT_NODES = (
    RouteNode('copper_west', 36.5, 36.5),
    RouteNode('copper_lane', 24.5, 36.5, 'stop'),
    RouteNode('oldtown_south', 36.5, 60.5),
    RouteNode('garden_approach', 48.5, 60.5),
    RouteNode('garden_stop', 48.5, 48.5, 'stop'),
    RouteNode('crossing_north', 60.5, 36.5),
    RouteNode('market_west', 68.5, 48.5),
    RouteNode('market_stop', 72.5, 48.5, 'stop'),
    RouteNode('market_outer', 75.0, 48.5),
    RouteNode('market_turn', 75.0, 48.0),
    RouteNode('market_top', 77.0, 48.0),
    RouteNode('market_lower', 77.0, 50.0),
    RouteNode('market_lower_west', 60.5, 50.0),
    RouteNode('market_south', 60.5, 60.5),
    RouteNode('crossing_center', 60.5, 72.5),
    RouteNode('canal_north', 60.5, 84.5),
    RouteNode('canal_bank', 60.5, 87.5),
    RouteNode('canal_bridge_west', 56.5, 89.5, 'bridge'),
    RouteNode('canal_bridge_mid', 60.5, 89.5, 'bridge'),
    RouteNode('canal_bridge_east', 64.5, 89.5, 'bridge'),
    RouteNode('canal_bridge_south', 60.5, 94.5, 'bridge'),
    RouteNode('canal_south', 60.5, 96.5),
    RouteNode('glass_north', 84.5, 24.5),
    RouteNode('glass_stop', 84.5, 36.5, 'stop'),
    RouteNode('glass_market', 84.5, 48.5),
)

# Each polyline is a manually chosen walkable corridor. Adjacent nodes on the
# same corridor are linked only if every sampled point remains walkable.
_DEFAULT_CHAINS = (
    ('copper_west', 'copper_lane'),
    ('copper_west', 'oldtown_south', 'garden_approach'),
    ('garden_approach', 'garden_stop'),
    ('copper_west', 'crossing_north', 'market_south', 'crossing_center',
     'canal_north', 'canal_bank'),
    ('crossing_north', 'market_lower_west', 'market_lower', 'market_turn',
     'market_outer', 'market_stop'),
    ('market_turn', 'market_top', 'market_lower'),
    ('glass_market', 'market_turn'),
    ('canal_bank', 'canal_bridge_mid', 'canal_bridge_south', 'canal_south'),
    ('canal_bridge_west', 'canal_bridge_mid', 'canal_bridge_east'),
    ('glass_north', 'glass_stop', 'glass_market'),
)


class NavigationGraph:
    """Validated sparse graph with deterministic shortest-path queries."""

    def __init__(self, city, *, nodes: Iterable[RouteNode] = _DEFAULT_NODES,
                 chains: Iterable[Iterable[str]] = _DEFAULT_CHAINS,
                 safe_stops: Iterable[str] = ('market_stop', 'canal_bridge_mid',
                                              'garden_stop', 'copper_lane')):
        authored = tuple(nodes)
        self.nodes = {node.id: node for node in authored
                      if node.kind in ('sidewalk', 'bridge', 'stop')
                      and _finite_node(node) and _walkable(city, node.x, node.y)}
        self.adjacency: dict[str, dict[str, float]] = {key: {} for key in self.nodes}
        for chain in chains:
            valid_chain = [node_id for node_id in chain if node_id in self.nodes]
            for left, right in zip(valid_chain, valid_chain[1:]):
                a, b = self.nodes[left], self.nodes[right]
                if self._edge_valid(city, a, b):
                    cost = math.hypot(a.x - b.x, a.y - b.y)
                    self.adjacency[left][right] = cost
                    self.adjacency[right][left] = cost
        self.safe_stops = tuple(stop for stop in safe_stops
                                if stop in self.nodes and self.nodes[stop].kind == 'stop'
                                or stop in self.nodes and self.nodes[stop].kind == 'bridge')

    @staticmethod
    def _edge_valid(city, a: RouteNode, b: RouteNode) -> bool:
        distance = math.hypot(b.x - a.x, b.y - a.y)
        samples = max(1, math.ceil(distance / .35))
        for index in range(samples + 1):
            ratio = index / samples
            if not _walkable(city, a.x + (b.x-a.x)*ratio,
                             a.y + (b.y-a.y)*ratio):
                return False
        return True

    def route(self, city, start: tuple[float, float], goal: tuple[float, float], *,
              fallback: tuple[float, float] | None = None) -> Route | None:
        """Find the shortest validated route; use a reachable safe stop on failure.

        Start and goal are retained as endpoints only when the straight connector
        to the selected graph node is itself walkable. A supplied fallback is
        considered after the graph's authored safe stops.
        """
        if not _finite_point(start) or not _finite_point(goal):
            return None
        start_node = self._nearest(city, start)
        if start_node is None:
            return None
        candidates: list[tuple[str, bool]] = []
        requested = self._nearest(city, goal)
        if requested is not None:
            candidates.append((requested[0], False))
        for safe_id in self.safe_stops:
            if safe_id != (requested or ''):
                candidates.append((safe_id, True))
        if fallback is not None and _finite_point(fallback):
            fallback_node = self._nearest(city, fallback)
            if fallback_node is not None:
                candidates.append((fallback_node[0], True))

        start_id, start_connector = start_node
        for target_id, is_fallback in candidates:
            path = self._shortest(start_id, target_id)
            if path is None:
                continue
            route_nodes = [self.nodes[node_id] for node_id in path]
            points = [(start[0], start[1])]
            if start_connector and (route_nodes[0].x, route_nodes[0].y) != start:
                points.append((route_nodes[0].x, route_nodes[0].y))
            points.extend((node.x, node.y) for node in route_nodes)
            target = route_nodes[-1]
            if not is_fallback:
                if self._edge_valid(city, target, RouteNode('_goal', *goal)):
                    points.append((goal[0], goal[1]))
                else:
                    is_fallback = True
            # De-duplicate consecutive points while preserving deterministic order.
            compact = tuple(point for index, point in enumerate(points)
                            if index == 0 or point != points[index-1])
            return Route(compact, tuple(path), target_id, is_fallback)
        return None

    def _nearest(self, city, point: tuple[float, float]):
        valid = []
        for node_id, node in self.nodes.items():
            if self._edge_valid(city, node, RouteNode('_point', *point)):
                valid.append((math.hypot(node.x-point[0], node.y-point[1]), node_id))
        if not valid:
            return None
        _, node_id = min(valid, key=lambda item: (item[0], item[1]))
        node = self.nodes[node_id]
        return node_id, (node.x, node.y) != point

    def _shortest(self, start: str, goal: str) -> tuple[str, ...] | None:
        if start not in self.nodes or goal not in self.nodes:
            return None
        queue = [(0.0, start)]
        costs = {start: 0.0}
        previous: dict[str, str] = {}
        while queue:
            cost, current = heapq.heappop(queue)
            if cost > costs[current] + 1e-12:
                continue
            if current == goal:
                result = [current]
                while current in previous:
                    current = previous[current]
                    result.append(current)
                return tuple(reversed(result))
            for neighbor, edge_cost in sorted(self.adjacency[current].items()):
                candidate = cost + edge_cost
                if candidate < costs.get(neighbor, math.inf) - 1e-12:
                    costs[neighbor] = candidate
                    previous[neighbor] = current
                    heapq.heappush(queue, (candidate, neighbor))
        return None


def _finite_node(node: RouteNode) -> bool:
    return bool(node.id) and all(math.isfinite(value) for value in (node.x, node.y))


def _finite_point(point: tuple[float, float]) -> bool:
    return (len(point) == 2 and all(isinstance(value, (int, float))
            and not isinstance(value, bool) and math.isfinite(value) for value in point))


def _walkable(city, x: float, y: float) -> bool:
    return city.walkable(x, y)
