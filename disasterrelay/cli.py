"""DisasterRelay command-line interface.

Commands:
    demo                 Run the bundled 6-node disaster demo out of the box.
    run-scenario FILE    Run a custom scenario JSON (same schema as demo_scenario/).
    graph                Render the demo mesh topology to a PNG.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .message import Message, Priority
from .mesh import MeshNetwork
from .report import DeliveryReport
from .simulator import RelaySimulator
from . import visualize

HERE = Path(__file__).resolve().parent.parent
SCENARIO_DIR = HERE / "demo_scenario"
ASSETS_DIR = HERE / "assets"


def load_scenario(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_mesh(spec: dict) -> MeshNetwork:
    mesh = MeshNetwork()
    for node in spec["nodes"]:
        if isinstance(node, dict):
            mesh.add_node(node["id"], node.get("label"))
        else:
            mesh.add_node(node)
    for a, b in spec["links"]:
        mesh.add_link(a, b)
    return mesh


def ascii_mesh(mesh: MeshNetwork) -> str:
    lines = ["  Mesh topology (links):"]
    for nid in mesh.nodes:
        nbrs = ", ".join(mesh.neighbors(nid, alive_only=False))
        mark = "ONLINE " if mesh.is_alive(nid) else "OFFLINE"
        lines.append(f"    [{mark}] {nid} ({mesh.label(nid)}) <-> {nbrs}")
    return "\n".join(lines)


def run_demo(scenario_path: Path | None = None,
             state_dir: Path | None = None,
             quiet: bool = False) -> DeliveryReport:
    scenario_path = scenario_path or (SCENARIO_DIR / "scenario.json")
    spec = load_scenario(scenario_path)
    mesh = build_mesh(spec)

    state_dir = state_dir or (SCENARIO_DIR / "state")
    if state_dir.exists():
        shutil.rmtree(state_dir)  # demos always start from a clean slate
    sim = RelaySimulator(mesh, state_dir)

    out = print if not quiet else (lambda *a, **k: None)
    out("=" * 64)
    out("  DISASTERRELAY -- offline-first emergency mesh messenger")
    out("  Scenario: earthquake knocks out cell towers; volunteers relay")
    out("  SOS / medical / info traffic over a 6-node radio mesh.")
    out("=" * 64)
    out(ascii_mesh(mesh))
    out("")

    pending_sends = sorted(spec["messages"], key=lambda m: m["send_tick"])
    drop_spec = spec.get("drop")
    revive_spec = spec.get("revive")
    max_ticks = int(spec.get("max_ticks", 60))

    dropped_done = False
    revived_done = False
    while sim.tick_count < max_ticks:
        # inject messages scheduled for this tick
        while pending_sends and pending_sends[0]["send_tick"] <= sim.tick_count:
            m = pending_sends.pop(0)
            sim.send(Message(id=m["id"], src=m["src"], dst=m["dst"],
                             priority=Priority.from_name(m["priority"]),
                             body=m["body"]))

        # mid-demo node failure -> the mesh must reroute around it
        if drop_spec and not dropped_done and sim.tick_count >= drop_spec["at_tick"]:
            out("")
            out(sim.drop_node(drop_spec["node"]))
            out("  >>> every later forward recomputes BFS around the dead node")
            out("  >>> watch for [REROUTE] -- live detours, no message lost")
            out("")
            dropped_done = True

        # the failed node comes back -> stranded store-and-forward mail resumes
        if revive_spec and not revived_done and sim.tick_count >= revive_spec["at_tick"]:
            out("")
            out(sim.revive_node(revive_spec["node"]))
            out("")
            revived_done = True

        events = sim.step()
        for e in events:
            if not quiet:
                # keep the tick log readable: always show deliveries/drops,
                # forwards only while the drama is on
                if ("DELIVERED" in e or "DROP" in e or "***" in e
                        or "REROUTE" in e or "HOLD" in e
                        or sim.tick_count <= 6 or dropped_done):
                    out("  " + e)

        if not pending_sends and sim.pending_count() == 0:
            break

    out("")
    report = DeliveryReport(sim)
    out(report.to_text())

    saved = report.save(SCENARIO_DIR)
    out(f"\nReport saved: {saved['txt']}\n              {saved['json']}")

    # visuals from the *actual* run: draw the mesh as it looked during the
    # outage (dropped node red) with a rerouted SOS path highlighted.
    down = {drop_spec["node"]} if (drop_spec and dropped_done) else set()
    sos_paths = [r.path for r in sim.delivered if r.priority == "SOS"]
    dodging = [p for p in sos_paths if not (set(p) & down)] or sos_paths
    highlight = max(dodging, key=len) if dodging else []
    g1 = visualize.draw_mesh(
        mesh, highlight_path=highlight,
        out_path=ASSETS_DIR / "mesh_graph.png",
        title="DisasterRelay mesh during the outage",
        offline=down,
    )
    g2 = visualize.draw_delivery_chart(report, ASSETS_DIR / "delivery_chart.png")
    out(f"Mesh graph   : {g1}\nDelivery chart: {g2}")
    return report


def cmd_graph(_args: argparse.Namespace) -> int:
    spec = load_scenario(SCENARIO_DIR / "scenario.json")
    mesh = build_mesh(spec)
    path = visualize.draw_mesh(mesh, out_path=ASSETS_DIR / "mesh_graph.png")
    print(f"wrote {path}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    run_demo(quiet=args.quiet)
    return 0


def cmd_run_scenario(args: argparse.Namespace) -> int:
    spec_path = Path(args.file)
    out_dir = Path(args.out)
    spec = load_scenario(spec_path)
    mesh = build_mesh(spec)
    state_dir = out_dir / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    sim = RelaySimulator(mesh, state_dir)
    for m in sorted(spec["messages"], key=lambda x: x["send_tick"]):
        sim.send(Message(id=m["id"], src=m["src"], dst=m["dst"],
                         priority=Priority.from_name(m["priority"]),
                         body=m["body"]))
    sim.run(int(spec.get("max_ticks", 100)))
    report = DeliveryReport(sim)
    print(report.to_text())
    saved = report.save(out_dir)
    print(f"saved {saved['txt']} and {saved['json']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="disasterrelay",
        description="Offline-first emergency mesh messenger (demo + tools).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="run the bundled 6-node disaster demo")
    p_demo.add_argument("--quiet", action="store_true",
                        help="only print the final report")
    p_demo.set_defaults(func=cmd_demo)

    p_run = sub.add_parser("run-scenario", help="run a custom scenario JSON")
    p_run.add_argument("file", help="scenario JSON file")
    p_run.add_argument("--out", default="scenario_out",
                       help="output directory for the report")
    p_run.set_defaults(func=cmd_run_scenario)

    p_graph = sub.add_parser("graph", help="render the demo mesh topology PNG")
    p_graph.set_defaults(func=cmd_graph)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
