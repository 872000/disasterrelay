"""Resilience: the mesh reroutes when a node drops; nothing is silently lost."""
import pytest

from disasterrelay.message import Message, Priority
from disasterrelay.mesh import MeshNetwork
from disasterrelay.simulator import RelaySimulator


def build_mesh() -> MeshNetwork:
    mesh = MeshNetwork()
    for a, b in [("A", "B"), ("B", "C"), ("C", "D"),
                 ("A", "E"), ("E", "F"), ("F", "D"), ("B", "E")]:
        mesh.add_link(a, b)
    return mesh


def send(mesh_src: str, dst: str, mid: str, prio: str, sim: RelaySimulator):
    sim.send(Message(id=mid, src=mesh_src, dst=dst,
                     priority=Priority.from_name(prio), body=mid))


def test_message_reroutes_around_dropped_node(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    send("A", "D", "m1", "SOS", sim)
    sim.step()  # A -> B
    sim.drop_node("C")  # primary B-C-D path now broken
    sim.run(30)
    assert sim.pending_count() == 0
    assert len(sim.dropped) == 0
    rec = sim.delivered[0]
    assert rec.msg_id == "m1"
    assert "C" not in rec.path  # rerouted via B-E-F-D
    assert rec.path == ["A", "B", "E", "F", "D"]


def test_stranded_messages_stay_pending_not_lost(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    send("A", "D", "m1", "INFO", sim)
    sim.step()  # A -> B, message now sits in B's store
    assert "m1" in sim.stores["B"]
    sim.drop_node("B")  # holder goes down with the message inside
    sim.run(10)
    # message is neither delivered nor dropped: store-and-forward holds it
    assert sim.pending_count() == 1
    assert len(sim.dropped) == 0
    assert len(sim.delivered) == 0
    # node comes back -> delivery resumes, nothing was lost
    sim.mesh.revive_node("B")
    sim.run(30)
    assert sim.pending_count() == 0
    assert [r.msg_id for r in sim.delivered] == ["m1"]


def test_partitioned_message_held_until_path_returns(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    sim.drop_node("C")
    sim.drop_node("E")  # A cut off from D entirely
    send("A", "D", "m1", "SOS", sim)
    sim.run(10)
    assert sim.pending_count() == 1  # held, not dropped
    sim.mesh.revive_node("E")
    sim.run(30)
    assert [r.msg_id for r in sim.delivered] == ["m1"]


def test_sos_delivered_before_info_from_same_node(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    send("A", "B", "info1", "INFO", sim)
    send("A", "B", "sos1", "SOS", sim)
    sim.step()
    delivered_ids = [r.msg_id for r in sim.delivered]
    assert delivered_ids == ["sos1"]  # SOS jumped the queue at A
    sim.step()
    assert [r.msg_id for r in sim.delivered] == ["sos1", "info1"]


def test_send_to_unknown_node_raises(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    with pytest.raises(KeyError):
        sim.send(Message(id="x", src="ZZZ", dst="A",
                         priority=Priority.SOS, body="x"))


def test_unknown_source_error_names_valid_nodes(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    with pytest.raises(KeyError) as exc_info:
        sim.send(Message(id="x", src="ZZZ", dst="A",
                         priority=Priority.SOS, body="x"))
    # the error tells the operator which node ids exist, so a typo is
    # spotted immediately instead of guessing from the mesh layout
    assert "valid nodes" in str(exc_info.value)
    for node in ["A", "B", "C", "D", "E", "F"]:
        assert node in str(exc_info.value)


def test_one_hop_per_tick(tmp_path):
    sim = RelaySimulator(build_mesh(), tmp_path / "state")
    send("A", "D", "m1", "INFO", sim)
    sim.step()
    # after exactly one tick the message moved exactly one hop: A -> B or A -> E
    assert sim.pending_count() == 1
    holders = [nid for nid, _ in sim.pending()]
    assert holders == ["B"] or holders == ["E"]
    _, m = sim.pending()[0]
    assert m.hops == 1
