"""Store-and-forward persistence: queues survive process restarts."""
from disasterrelay.message import Message, Priority
from disasterrelay.store import NodeStore


def msg(mid: str, prio: str = "SOS") -> Message:
    return Message(id=mid, src="A", dst="B",
                   priority=Priority.from_name(prio), body="body " + mid)


def test_messages_survive_reload(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(msg("m1", "SOS"))
    store.enqueue(msg("m2", "INFO"))

    reloaded = NodeStore("A", tmp_path)  # new instance, same dir on disk
    assert len(reloaded) == 2
    assert reloaded.dequeue().id == "m1"  # priority order preserved
    assert reloaded.dequeue().id == "m2"


def test_dequeue_persists_removal(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(msg("m1"))
    store.dequeue()
    assert len(NodeStore("A", tmp_path)) == 0


def test_seq_continues_after_reload(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(msg("m1", "INFO"))
    reloaded = NodeStore("A", tmp_path)
    reloaded.enqueue(msg("m2", "INFO"))
    # FIFO order must be m1 then m2 even across the reload boundary
    assert [m.id for m in reloaded.peek_all()] == ["m1", "m2"]


def test_corrupt_file_does_not_crash(tmp_path):
    p = tmp_path / "node_A.json"
    p.write_text("{ not valid json", encoding="utf-8")
    store = NodeStore("A", tmp_path)
    assert len(store) == 0
    store.enqueue(msg("m1"))
    assert len(store) == 1


def test_remove_message(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(msg("m1"))
    store.enqueue(msg("m2"))
    assert store.remove("m1").id == "m1"
    assert store.remove("missing") is None
    assert [m.id for m in store.peek_all()] == ["m2"]
