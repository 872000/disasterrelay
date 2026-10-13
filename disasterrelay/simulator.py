"""Tick-based relay simulation over the mesh.

Each tick, every alive node forwards at most one message: the highest
priority one in its store. Forwarding recomputes the BFS shortest path from
the *current holder*, so when a node drops out mid-simulation the remaining
messages automatically reroute around it on the very next tick.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .message import Message, Priority
from .mesh import MeshNetwork
from .store import NodeStore


@dataclass
class DeliveryRecord:
    msg_id: str
    src: str
    dst: str
    priority: str
    hops: int
    latency_ticks: int
    path: List[str] = field(default_factory=list)


class RelaySimulator:
    def __init__(self, mesh: MeshNetwork, state_dir: str | Path) -> None:
        self.mesh = mesh
        self.state_dir = Path(state_dir)
        self.stores: Dict[str, NodeStore] = {
            nid: NodeStore(nid, self.state_dir) for nid in mesh.nodes
        }
        self.tick_count = 0
        self.delivered: List[DeliveryRecord] = []
        self.dropped: List[DeliveryRecord] = []
        self.events: List[str] = []  # human-readable log of what happened

    # -- messaging ---------------------------------------------------------
    def send(self, msg: Message) -> None:
        """Inject a message into its source node's store."""
        if msg.src not in self.stores:
            raise KeyError(f"unknown source node {msg.src!r}; "
                           f"valid nodes: {', '.join(self.mesh.nodes)}")
        msg.created_tick = self.tick_count
        msg.path = [msg.src]
        msg.plan = self.mesh.shortest_path(msg.src, msg.dst) or []
        self.stores[msg.src].enqueue(msg)
        self.events.append(
            f"[t={self.tick_count}] SEND {msg.id} {msg.priority.name} "
            f"{msg.src}->{msg.dst}: {msg.body}"
        )

    # -- simulation --------------------------------------------------------
    def step(self) -> List[str]:
        """Advance one tick. Returns the event lines produced this tick."""
        self.tick_count += 1
        tick_events: List[str] = []

        # Snapshot one candidate message per alive node *before* any forwarding,
        # so a message can only travel one hop per tick (realistic radio timing).
        candidates: List[tuple[str, Message]] = []
        for node_id in self.mesh.alive_nodes():
            msg = self.stores[node_id].dequeue()
            if msg is not None:
                candidates.append((node_id, msg))

        for node_id, msg in candidates:
            line = self._forward(node_id, msg)
            if line:
                tick_events.append(line)
                self.events.append(line)
        return tick_events

    def _forward(self, holder: str, msg: Message) -> Optional[str]:
        # TTL counts hops: an SOS may wander further looking for a path.
        if msg.hops >= msg.priority.ttl:
            self.dropped.append(
                DeliveryRecord(
                    msg.id, msg.src, msg.dst, msg.priority.name,
                    msg.hops, self.tick_count - msg.created_tick, list(msg.path),
                )
            )
            return (
                f"[t={self.tick_count}] DROP {msg.id} ({msg.priority.name}) "
                f"TTL exceeded after {msg.hops} hops; last at {holder}"
            )

        path = self.mesh.shortest_path(holder, msg.dst)
        if path is None:
            # No route right now: store-and-forward holds it for a later tick.
            self.stores[holder].enqueue(msg)
            return (
                f"[t={self.tick_count}] HOLD {msg.id} ({msg.priority.name}) "
                f"at {holder}: no route to {msg.dst}, kept in store"
            )

        next_hop = path[1]
        msg.hops += 1
        msg.path.append(next_hop)

        # A genuine reroute: the message deviates from the shortest path
        # planned at send time (e.g. a node on that path just died).
        rerouted = False
        if holder in msg.plan:
            planned_next = msg.plan[msg.plan.index(holder) + 1]
            rerouted = planned_next != next_hop
        reroute = " [REROUTE]" if rerouted else ""

        if next_hop == msg.dst:
            self.delivered.append(
                DeliveryRecord(
                    msg.id, msg.src, msg.dst, msg.priority.name,
                    msg.hops, self.tick_count - msg.created_tick, list(msg.path),
                )
            )
            return (
                f"[t={self.tick_count}] DELIVERED {msg.id} ({msg.priority.name}) "
                f"{msg.src}->{msg.dst} in {msg.hops} hops{reroute} "
                f"(latency {self.tick_count - msg.created_tick} ticks) "
                f"via {' > '.join(msg.path)}"
            )

        self.stores[next_hop].enqueue(msg)
        return (
            f"[t={self.tick_count}] FWD {msg.id} ({msg.priority.name}) "
            f"{holder} -> {next_hop}{reroute} "
            f"(route: {' > '.join(path)})"
        )

    def run(self, max_ticks: int = 100) -> None:
        """Run until every message is delivered/dropped or ticks run out."""
        for _ in range(max_ticks):
            if self.pending_count() == 0:
                break
            self.step()

    # -- node failure --------------------------------------------------------
    def drop_node(self, node_id: str) -> str:
        self.mesh.drop_node(node_id)
        stranded = len(self.stores[node_id])
        line = (
            f"[t={self.tick_count}] *** NODE {node_id} DROPPED OUT *** "
            f"({stranded} message(s) stranded in its store; "
            f"mesh reroutes around it)"
        )
        self.events.append(line)
        return line

    def revive_node(self, node_id: str) -> str:
        self.mesh.revive_node(node_id)
        queued = len(self.stores[node_id])
        line = (
            f"[t={self.tick_count}] *** NODE {node_id} BACK ONLINE *** "
            f"({queued} stranded message(s) resume from its store)"
        )
        self.events.append(line)
        return line

    # -- inspection ----------------------------------------------------------
    def pending(self) -> List[tuple[str, Message]]:
        """(node_id, message) for everything still in flight."""
        out: List[tuple[str, Message]] = []
        for nid in self.mesh.nodes:
            for msg in self.stores[nid].peek_all():
                out.append((nid, msg))
        return out

    def pending_count(self) -> int:
        return sum(len(s) for s in self.stores.values())
