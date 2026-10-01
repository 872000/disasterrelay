"""Persistent per-node store-and-forward queues.

Each mesh node owns a JSON-backed outbox on disk. Messages survive process
restarts and node outages: a message is only removed from a node's store
once it has been handed to the next hop (or delivered / dropped).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .message import Message, Priority


class NodeStore:
    """Disk-persistent priority queue for one mesh node."""

    def __init__(self, node_id: str, state_dir: str | Path) -> None:
        self.node_id = node_id
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / f"node_{node_id}.json"
        self._messages: Dict[str, Message] = {}
        self._next_seq = 0
        self.load()

    # -- queue ops ---------------------------------------------------------
    def enqueue(self, msg: Message) -> Message:
        """Append a message; assigns a FIFO sequence number and persists."""
        msg.seq = self._next_seq
        self._next_seq += 1
        self._messages[msg.id] = msg
        self.save()
        return msg

    def dequeue(self) -> Optional[Message]:
        """Pop the highest-priority message (SOS > MEDICAL > INFO, FIFO within)."""
        if not self._messages:
            return None
        top = self.peek_all()[0]
        del self._messages[top.id]
        self.save()
        return top

    def peek_all(self) -> List[Message]:
        """All queued messages in service order without removing them."""
        return sorted(
            self._messages.values(),
            key=lambda m: (-m.priority.value, m.seq),
        )

    def remove(self, msg_id: str) -> Optional[Message]:
        msg = self._messages.pop(msg_id, None)
        if msg is not None:
            self.save()
        return msg

    def __len__(self) -> int:
        return len(self._messages)

    def __contains__(self, msg_id: str) -> bool:
        return msg_id in self._messages

    # -- persistence ---------------------------------------------------------
    def save(self) -> None:
        payload = {
            "node_id": self.node_id,
            "next_seq": self._next_seq,
            "messages": [m.to_dict() for m in self._messages.values()],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic so a crash can't corrupt the store

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return  # keep whatever is in memory; never crash on a bad file
        self._next_seq = int(payload.get("next_seq", 0))
        self._messages = {}
        for item in payload.get("messages", []):
            try:
                msg = Message.from_dict(item)
            except (KeyError, ValueError, TypeError):
                continue
            self._messages[msg.id] = msg
            self._next_seq = max(self._next_seq, msg.seq + 1)
