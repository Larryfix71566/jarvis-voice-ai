"""Tests for jarvis.graphs.render (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 7, §7)."""
import math
from io import BytesIO

from PIL import Image

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node
from jarvis.graphs import render

W, H = gcfg.GRAPH_IMAGE_W, gcfg.GRAPH_IMAGE_H


def _fixture_graph() -> Graph:
    g = Graph("federated")
    g.add_node(Node("run:r1", "run", "r1"))
    g.add_node(Node("tool:t1", "tool", "t1"))
    g.add_node(Node("proposal:p", "proposal", "p"))
    g.add_node(Node("round:rd", "round", "rd"))
    g.add_node(Node("profile:j1", "profile", "j1"))
    g.add_node(Node("fact:k", "fact", "k", {"archived": True}))     # isolated + archived
    g.add_edge(Edge("run:r1", "tool:t1", "called", {"ok": 1}))
    g.add_edge(Edge("run:r1", "tool:t1", "called", {"ok": 0}))
    g.add_edge(Edge("proposal:p", "round:rd", "won", {}))
    g.add_edge(Edge("profile:j1", "proposal:p", "scored", {"superseded": True}))
    return g


def test_layout_is_deterministic_and_inside_margins():
    g = _fixture_graph()
    pos1 = render.layout(g, None, W, H)
    pos2 = render.layout(g, None, W, H)
    assert pos1 == pos2
    margin = gcfg.GRAPH_MARGIN_PX
    for x, y in pos1.values():
        assert margin + gcfg.GRAPH_LEGEND_W_PX <= x <= W - margin
        assert margin <= y <= H - margin


def test_layout_spreads_disconnected_components():
    g = Graph("memory")
    for nid in ("a1", "a2", "a3", "b1", "b2", "b3"):
        g.add_node(Node(nid, "fact", nid))
    g.add_edge(Edge("a1", "a2", "child_of"))
    g.add_edge(Edge("a2", "a3", "child_of"))
    g.add_edge(Edge("b1", "b2", "child_of"))
    g.add_edge(Edge("b2", "b3", "child_of"))
    pos = render.layout(g, None, W, H)
    ids = list(pos)
    min_dist = min(
        math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])
        for a, i in enumerate(ids) for j in ids[a + 1:]
    )
    assert min_dist >= 2 * gcfg.GRAPH_NODE_RADIUS_PX


def test_isolated_nodes_sit_on_bottom_row():
    g = _fixture_graph()
    pos = render.layout(g, None, W, H)
    assert pos["fact:k"][1] == H - gcfg.GRAPH_MARGIN_PX


def test_svg_contains_every_node_and_edge_and_legend():
    g = _fixture_graph()
    pos = render.layout(g, None, W, H)
    svg = render.to_svg(g, pos, W, H)
    legend = render.legend_for(g.name)
    assert svg.count("<circle") == len(g.nodes) + len(legend["node_types"])
    assert svg.count("<line") == len(g.edges) + len(legend["edge_types"])
    for t in legend["node_types"]:
        assert t in svg
    for t in legend["edge_types"]:
        assert t in svg


def test_failed_called_edge_is_red_in_svg():
    g = _fixture_graph()
    pos = render.layout(g, None, W, H)
    svg = render.to_svg(g, pos, W, H)
    assert svg.count('stroke="#f85149"') == 1


def test_superseded_edge_is_faded_in_svg():
    g = _fixture_graph()
    pos = render.layout(g, None, W, H)
    svg = render.to_svg(g, pos, W, H)
    assert 'stroke-opacity="0.45"' in svg


def test_png_decodes_to_requested_size():
    g = _fixture_graph()
    pos = render.layout(g, None, W, H)
    png = render.to_png(g, pos, W, H)
    img = Image.open(BytesIO(png))
    assert img.size == (W, H)


def test_error_image_has_text_and_no_nodes():
    svg = render.error_image_svg("graphs are disabled", W, H)
    assert "graphs are disabled" in svg
    assert "<circle" not in svg
    png = render.error_image_png("graphs are disabled", W, H)
    img = Image.open(BytesIO(png))
    assert img.size == (W, H)


def test_two_renders_byte_identical():
    g = _fixture_graph()
    pos1 = render.layout(g, None, W, H)
    pos2 = render.layout(g, None, W, H)
    png1 = render.to_png(g, pos1, W, H)
    png2 = render.to_png(g, pos2, W, H)
    assert png1 == png2
    svg1 = render.to_svg(g, pos1, W, H)
    svg2 = render.to_svg(g, pos2, W, H)
    assert svg1 == svg2


def test_legend_for_federated_is_union():
    legend = render.legend_for("federated")
    all_types: set[str] = set()
    for name in ("memory", "capability", "execution", "deliberation"):
        all_types |= set(render.GRAPH_NODE_TYPES[name])
    assert set(legend["node_types"]) == all_types
