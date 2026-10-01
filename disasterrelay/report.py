"""Delivery reports: counts, hop counts and per-message latency."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .simulator import DeliveryRecord, RelaySimulator


class DeliveryReport:
    def __init__(self, sim: RelaySimulator) -> None:
        self.sim = sim
        self.ticks = sim.tick_count

    # -- aggregates ----------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        delivered = self.sim.delivered
        pending = self.sim.pending()
        dropped = self.sim.dropped

        def stats(records: List[DeliveryRecord], key: str) -> Dict[str, Any]:
            vals = [getattr(r, key) for r in records]
            if not vals:
                return {"avg": 0.0, "max": 0, "min": 0}
            return {
                "avg": round(sum(vals) / len(vals), 2),
                "max": max(vals),
                "min": min(vals),
            }

        by_priority: Dict[str, int] = {}
        for r in delivered:
            by_priority[r.priority] = by_priority.get(r.priority, 0) + 1

        total = len(delivered) + len(pending) + len(dropped)
        return {
            "ticks_elapsed": self.ticks,
            "total_messages": total,
            "delivered": len(delivered),
            "pending": len(pending),
            "dropped": len(dropped),
            "delivery_rate": round(len(delivered) / total, 3) if total else 0.0,
            "delivered_by_priority": by_priority,
            "latency_ticks": stats(delivered, "latency_ticks"),
            "hop_counts": stats(delivered, "hops"),
        }

    def message_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for r in self.sim.delivered:
            rows.append({
                "id": r.msg_id, "status": "DELIVERED", "priority": r.priority,
                "route": " > ".join(r.path), "hops": r.hops,
                "latency_ticks": r.latency_ticks,
            })
        for node_id, m in self.sim.pending():
            rows.append({
                "id": m.id, "status": "PENDING", "priority": m.priority.name,
                "route": " > ".join(m.path) + f" ... (held at {node_id})",
                "hops": m.hops,
                "latency_ticks": self.ticks - m.created_tick,
            })
        for r in self.sim.dropped:
            rows.append({
                "id": r.msg_id, "status": "DROPPED", "priority": r.priority,
                "route": " > ".join(r.path), "hops": r.hops,
                "latency_ticks": r.latency_ticks,
            })
        return rows

    # -- rendering -------------------------------------------------------------
    def to_text(self) -> str:
        s = self.summary()
        lines = [
            "=" * 60,
            "DISASTERRELAY DELIVERY REPORT",
            "=" * 60,
            f"Ticks elapsed : {s['ticks_elapsed']}",
            f"Total messages: {s['total_messages']}",
            f"Delivered     : {s['delivered']}",
            f"Pending       : {s['pending']}",
            f"Dropped       : {s['dropped']}",
            f"Delivery rate : {s['delivery_rate'] * 100:.1f}%",
            "",
            "Delivered by priority : "
            + ", ".join(f"{k}={v}" for k, v in sorted(s["delivered_by_priority"].items())),
            f"Latency (ticks)       : avg {s['latency_ticks']['avg']}, "
            f"max {s['latency_ticks']['max']}, min {s['latency_ticks']['min']}",
            f"Hop counts            : avg {s['hop_counts']['avg']}, "
            f"max {s['hop_counts']['max']}, min {s['hop_counts']['min']}",
            "",
            "-" * 60,
            f"{'ID':<8}{'STATUS':<10}{'PRIO':<9}{'HOPS':<6}{'LAT':<5}ROUTE",
            "-" * 60,
        ]
        for row in self.message_rows():
            lines.append(
                f"{row['id']:<8}{row['status']:<10}{row['priority']:<9}"
                f"{row['hops']:<6}{row['latency_ticks']:<5}{row['route']}"
            )
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary(), "messages": self.message_rows()}

    def save(self, out_dir: str | Path) -> Dict[str, str]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        txt_path = out_dir / "delivery_report.txt"
        json_path = out_dir / "delivery_report.json"
        txt_path.write_text(self.to_text(), encoding="utf-8")
        json_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return {"txt": str(txt_path), "json": str(json_path)}
