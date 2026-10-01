"""Delivery report: counts, latency and hop stats, text/JSON output."""
import json

from disasterrelay.message import Message, Priority
from disasterrelay.mesh import MeshNetwork
from disasterrelay.report import DeliveryReport
from disasterrelay.simulator import RelaySimulator


def run_sim(tmp_path) -> RelaySimulator:
    mesh = MeshNetwork()
    for a, b in [("A", "B"), ("B", "D"), ("A", "C"), ("C", "D")]:
        mesh.add_link(a, b)
    sim = RelaySimulator(mesh, tmp_path / "state")
    sim.send(Message(id="s1", src="A", dst="D", priority=Priority.SOS, body="sos"))
    sim.send(Message(id="i1", src="A", dst="D", priority=Priority.INFO, body="info"))
    sim.run(30)
    return sim


def test_report_counts_add_up(tmp_path):
    sim = run_sim(tmp_path)
    report = DeliveryReport(sim)
    s = report.summary()
    assert s["total_messages"] == 2
    assert s["delivered"] + s["pending"] + s["dropped"] == s["total_messages"]
    assert s["delivered"] == 2
    assert s["delivery_rate"] == 1.0


def test_report_latency_and_hops_sane(tmp_path):
    sim = run_sim(tmp_path)
    s = DeliveryReport(sim).summary()
    assert s["latency_ticks"]["avg"] >= s["hop_counts"]["avg"] >= 1
    assert s["latency_ticks"]["max"] >= s["latency_ticks"]["min"]


def test_report_by_priority(tmp_path):
    sim = run_sim(tmp_path)
    by_prio = DeliveryReport(sim).summary()["delivered_by_priority"]
    assert by_prio == {"SOS": 1, "INFO": 1}


def test_report_saves_text_and_json(tmp_path):
    sim = run_sim(tmp_path)
    report = DeliveryReport(sim)
    paths = report.save(tmp_path / "out")
    text = open(paths["txt"], encoding="utf-8").read()
    assert "DELIVERY REPORT" in text
    assert "s1" in text and "i1" in text
    data = json.loads(open(paths["json"], encoding="utf-8").read())
    assert data["summary"]["delivered"] == 2
    assert len(data["messages"]) == 2


def test_report_message_rows_cover_all_outcomes(tmp_path):
    sim = run_sim(tmp_path)
    rows = DeliveryReport(sim).message_rows()
    assert {r["status"] for r in rows} == {"DELIVERED"}
    assert all(r["hops"] >= 1 and r["latency_ticks"] >= 1 for r in rows)
