"""Priority triage: SOS > MEDICAL > INFO, FIFO within a priority class."""
from disasterrelay.message import Message, Priority
from disasterrelay.store import NodeStore


def make_msg(mid: str, priority: str) -> Message:
    return Message(id=mid, src="A", dst="B",
                   priority=Priority.from_name(priority), body=mid)


def test_sos_jumps_queue(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(make_msg("info1", "INFO"))
    store.enqueue(make_msg("med1", "MEDICAL"))
    store.enqueue(make_msg("sos1", "SOS"))
    assert store.dequeue().id == "sos1"
    assert store.dequeue().id == "med1"
    assert store.dequeue().id == "info1"
    assert store.dequeue() is None


def test_fifo_within_priority(tmp_path):
    store = NodeStore("A", tmp_path)
    for i in range(3):
        store.enqueue(make_msg(f"sos{i}", "SOS"))
    assert [store.dequeue().id for _ in range(3)] == ["sos0", "sos1", "sos2"]


def test_peek_does_not_remove(tmp_path):
    store = NodeStore("A", tmp_path)
    store.enqueue(make_msg("m1", "INFO"))
    assert [m.id for m in store.peek_all()] == ["m1"]
    assert len(store) == 1


def test_priority_from_name_case_insensitive():
    assert Priority.from_name("sos") is Priority.SOS
    assert Priority.from_name("Medical") is Priority.MEDICAL
    assert Priority.from_name("INFO") is Priority.INFO


def test_priority_ordering_values():
    assert Priority.SOS > Priority.MEDICAL > Priority.INFO
