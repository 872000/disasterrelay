"""Messages and priority levels for DisasterRelay.

Priority triage order: SOS > MEDICAL > INFO. Higher priority messages are
dequeued first at every node and get more generous TTL / retry budgets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List


class Priority(IntEnum):
    """Triage priority. Higher value == more urgent."""

    INFO = 1
    MEDICAL = 2
    SOS = 3

    @classmethod
    def from_name(cls, name: str) -> "Priority":
        try:
            return cls[name.strip().upper()]
        except KeyError:
            raise ValueError(f"unknown priority {name!r}; want SOS, MEDICAL or INFO")

    @property
    def ttl(self) -> int:
        """Max hops a message of this priority may take before being dropped."""
        return {Priority.SOS: 30, Priority.MEDICAL: 20, Priority.INFO: 12}[self]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.name


@dataclass
class Message:
    """A single store-and-forward message travelling the mesh."""

    id: str
    src: str
    dst: str
    priority: Priority
    body: str
    created_tick: int = 0
    hops: int = 0
    path: List[str] = field(default_factory=list)
    seq: int = 0  # enqueue order within a node store (FIFO tiebreak)
    plan: List[str] = field(default_factory=list)  # shortest path at send time

    def __post_init__(self) -> None:
        if isinstance(self.priority, str):
            self.priority = Priority.from_name(self.priority)
        if not self.path:
            self.path = [self.src]

    # -- persistence -----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "src": self.src,
            "dst": self.dst,
            "priority": self.priority.name,
            "body": self.body,
            "created_tick": self.created_tick,
            "hops": self.hops,
            "path": list(self.path),
            "seq": self.seq,
            "plan": list(self.plan),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        data = dict(data)
        data["priority"] = Priority.from_name(data["priority"])
        return cls(**data)
