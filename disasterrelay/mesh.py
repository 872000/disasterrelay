"""Mesh graph model and routing for DisasterRelay.

Routing is plain BFS (breadth-first search) over the alive nodes, so the
first path found is always a shortest-hop path. No A* heuristics needed:
every link costs 1, which makes BFS optimal and easy to verify.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set


class MeshNetwork:
    """Undirected graph of mesh nodes with liveness tracking."""

    def __init__(self) -> None:
        self._neighbors: Dict[str, Set[str]] = {}
        self._alive: Dict[str, bool] = {}
        self._labels: Dict[str, str] = {}

    # -- topology --------------------------------------------------------
    def add_node(self, node_id: str, label: str | None = None) -> None:
        self._neighbors.setdefault(node_id, set())
        self._alive.setdefault(node_id, True)
        self._labels[node_id] = label or node_id

    def add_link(self, a: str, b: str) -> None:
        for n in (a, b):
            if n not in self._neighbors:
                self.add_node(n)
        self._neighbors[a].add(b)
        self._neighbors[b].add(a)

    @property
    def nodes(self) -> List[str]:
        return sorted(self._neighbors)

    def neighbors(self, node_id: str, alive_only: bool = True) -> List[str]:
        nbrs = self._neighbors.get(node_id, set())
        if alive_only:
            nbrs = {n for n in nbrs if self._alive.get(n, False)}
        return sorted(nbrs)

    def label(self, node_id: str) -> str:
        return self._labels.get(node_id, node_id)

    # -- liveness ----------------------------------------------------------
    def drop_node(self, node_id: str) -> None:
        """Simulate a node going offline (battery dead, destroyed, out of range)."""
        if node_id not in self._neighbors:
            raise KeyError(f"unknown node {node_id!r}")
        self._alive[node_id] = False

    def revive_node(self, node_id: str) -> None:
        self._alive[node_id] = True

    def is_alive(self, node_id: str) -> bool:
        return self._alive.get(node_id, False)

    def alive_nodes(self) -> List[str]:
        return sorted(n for n in self._neighbors if self._alive[n])

    # -- routing -----------------------------------------------------------
    def shortest_path(self, src: str, dst: str) -> Optional[List[str]]:
        """BFS shortest path over alive nodes; None when unreachable.

        BFS on an unweighted graph always returns a minimum-hop path, so
        high-priority traffic automatically takes priority (shortest) routes
        and reroutes around dropped nodes without any heuristic search.
        """
        if src not in self._neighbors or dst not in self._neighbors:
            return None
        if not self.is_alive(src) or not self.is_alive(dst):
            return None
        if src == dst:
            return [src]
        prev: Dict[str, Optional[str]] = {src: None}
        queue: deque[str] = deque([src])
        while queue:
            cur = queue.popleft()
            for nxt in self.neighbors(cur, alive_only=True):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == dst:
                        path = [dst]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])  # type: ignore[arg-type]
                        return path[::-1]
                    queue.append(nxt)
        return None

    def reachable(self, src: str) -> Set[str]:
        """All nodes reachable from src over alive nodes (BFS flood)."""
        seen = {src} if self.is_alive(src) else set()
        queue: deque[str] = deque(seen)
        while queue:
            cur = queue.popleft()
            for nxt in self.neighbors(cur, alive_only=True):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen
