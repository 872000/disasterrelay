"""Routing correctness: BFS shortest paths, dead-node exclusion, no-path."""
import pytest

from disasterrelay.mesh import MeshNetwork


def make_mesh() -> MeshNetwork:
    mesh = MeshNetwork()
    # A - B - C - D chain plus A - E - F - D bypass, and B - E cross-link
    for a, b in [("A", "B"), ("B", "C"), ("C", "D"),
                 ("A", "E"), ("E", "F"), ("F", "D"), ("B", "E")]:
        mesh.add_link(a, b)
    return mesh


def test_shortest_path_prefers_fewer_hops():
    mesh = make_mesh()
    # A->D direct-ish: A-B-C-D is 3 hops, A-E-F-D is 3 hops, A-B-E-F-D is 4.
    path = mesh.shortest_path("A", "D")
    assert path is not None
    assert path[0] == "A" and path[-1] == "D"
    assert len(path) == 4  # 3 hops is minimal


def test_path_is_valid_walk():
    mesh = make_mesh()
    path = mesh.shortest_path("A", "D")
    assert path is not None
    for a, b in zip(path, path[1:]):
        assert b in mesh.neighbors(a, alive_only=False)


def test_src_equals_dst():
    mesh = make_mesh()
    assert mesh.shortest_path("A", "A") == ["A"]


def test_dead_nodes_excluded_from_routes():
    mesh = make_mesh()
    mesh.drop_node("C")
    path = mesh.shortest_path("A", "D")
    assert path is not None
    assert "C" not in path
    assert len(path) == 4  # reroutes via A-E-F-D


def test_no_path_returns_none():
    mesh = make_mesh()
    mesh.drop_node("C")
    mesh.drop_node("E")
    # A side {A,B} cut off from D side {D,F}
    assert mesh.shortest_path("A", "D") is None


def test_unknown_nodes_return_none():
    mesh = make_mesh()
    assert mesh.shortest_path("A", "ZZZ") is None
    assert mesh.shortest_path("ZZZ", "A") is None


def test_drop_unknown_node_raises():
    mesh = make_mesh()
    with pytest.raises(KeyError):
        mesh.drop_node("ZZZ")


def test_revive_restores_route():
    mesh = make_mesh()
    mesh.drop_node("B")
    mesh.drop_node("E")
    assert mesh.shortest_path("A", "D") is None
    mesh.revive_node("B")
    path = mesh.shortest_path("A", "D")
    assert path is not None and "B" in path
