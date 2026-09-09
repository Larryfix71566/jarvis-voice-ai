"""GL10 — one layout, two encoders, fixed palette. networkx is imported inside layout()."""
from __future__ import annotations

import math
from io import BytesIO
from xml.sax.saxutils import escape

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node

PALETTE = {
    "fact": "#5ec8ff", "prefix": "#2f6f8f", "turn": "#9aa5b1", "archive": "#4a5561",
    "run": "#7ee787", "session": "#3b6b3f", "agent": "#d2a8ff", "tool": "#ffa657",
    "model": "#f778ba", "procedure": "#79c0ff", "skill": "#a5d6ff", "workflow": "#56d4dd",
    "round": "#ffdf5d", "proposal": "#e3b341", "profile": "#f778ba",
    "doc": "#c9d1d9", "note": "#c9d1d9", "entity": "#ff7b72",
}
EDGE_STYLES = {
    "child_of": "solid", "in_session": "solid", "by_agent": "solid", "ran_on": "solid",
    "called": "solid", "proposed": "solid", "in_round": "solid", "learned_by": "solid",
    "for_agent": "solid",
    "became": "dashed", "promoted_from": "dashed", "extracted_from": "dashed",
    "learned_from": "dashed", "taught": "dashed", "stated_in": "dashed", "for_run": "dashed",
    "scored": "dotted", "restated": "dotted",
    "won": "won",
}
GRAPH_NODE_TYPES = {
    "memory": ("fact", "prefix", "turn", "archive", "workflow"),
    "capability": ("procedure", "skill", "workflow", "agent", "run", "fact"),
    "execution": ("run", "session", "agent", "tool", "model", "procedure"),
    "deliberation": ("round", "proposal", "profile", "run"),
}
GRAPH_EDGE_TYPES = {
    "memory": ("child_of", "became", "stated_in", "restated"),
    "capability": ("learned_by", "learned_from", "promoted_from", "for_agent", "extracted_from"),
    "execution": ("in_session", "by_agent", "ran_on", "called", "taught"),
    "deliberation": ("proposed", "scored", "won", "in_round", "for_run"),
}
BG, LABEL, EDGE, FOCUS_RING, FAIL = "#15191d", "#e6edf3", "#8b98a5", "#ffb454", "#f85149"
EDGE_ALPHA, FADED_ALPHA = 0.70, 0.45
FADED_STATUSES = {"deprecated", "failed", "timeout", "orphaned", "too_small"}
DASH = {"dashed": (8, 6), "dotted": (2, 5)}


def _names(name: str) -> tuple[str, ...]:
    return tuple(GRAPH_NODE_TYPES) if name == "federated" else (name,)


def legend_for(name: str) -> dict:
    node_types: dict[str, str] = {}
    edge_types: dict[str, str] = {}
    for n in _names(name):
        for t in GRAPH_NODE_TYPES.get(n, ()):
            node_types.setdefault(t, PALETTE[t])
        for t in GRAPH_EDGE_TYPES.get(n, ()):
            edge_types.setdefault(t, EDGE_STYLES[t])
    return {"node_types": node_types, "edge_types": edge_types}


def all_edge_types(name: str) -> list[str]:
    out: list[str] = []
    for n in _names(name):
        for t in GRAPH_EDGE_TYPES.get(n, ()):
            if t not in out:
                out.append(t)
    return out


def node_faded(node: Node) -> bool:
    a = node.attrs
    return bool(a.get("archived") is True or a.get("pruned") or a.get("missing") or a.get("invalid")
                or a.get("status") in FADED_STATUSES)


def edge_faded(edge: Edge) -> bool:
    return bool(edge.attrs.get("superseded"))


def edge_color(edge: Edge) -> str:
    if edge.type == "called" and edge.attrs.get("ok") == 0:
        return FAIL
    if edge.type == "won":
        return FOCUS_RING
    return EDGE


def _unit_layout(nx, sub, comp: list[str]) -> dict[str, tuple[float, float]]:
    """One connected component laid out into the unit square [0,1]², padded so cells never touch."""
    n = len(comp)
    if n == 1:
        return {comp[0]: (0.5, 0.5)}
    raw = nx.spring_layout(sub, seed=gcfg.GRAPH_LAYOUT_SEED,
                           k=gcfg.GRAPH_LAYOUT_K / max(1.0, math.sqrt(n)),
                           iterations=gcfg.GRAPH_LAYOUT_ITERATIONS)
    xs = [float(raw[nid][0]) for nid in comp]
    ys = [float(raw[nid][1]) for nid in comp]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    out = {}
    for nid in comp:
        fx = 0.5 if maxx == minx else (float(raw[nid][0]) - minx) / (maxx - minx)
        fy = 0.5 if maxy == miny else (float(raw[nid][1]) - miny) / (maxy - miny)
        out[nid] = (0.1 + 0.8 * fx, 0.1 + 0.8 * fy)
    return out


def layout(graph: Graph, focus: str | None, width: int, height: int) -> dict[str, tuple[float, float]]:
    """Deterministic layout inside the margins (GL10). Each connected component gets its own
    spring layout in a square cell whose side is √(component size); cells are packed into rows
    (largest first) and the packed rectangle is stretched onto the canvas — a single spring
    layout over a disconnected graph collapses every component into a blob (smoke test,
    2026-09-04). Isolated nodes go on a bottom row, left to right, in id order."""
    import networkx as nx

    margin = gcfg.GRAPH_MARGIN_PX
    ids = sorted(graph.nodes)
    adj = graph.adjacency()
    isolated = [nid for nid in ids if not adj[nid]]
    pos: dict[str, tuple[float, float]] = {}
    x0, x1 = float(margin + gcfg.GRAPH_LEGEND_W_PX), float(width - margin)   # legend column reserved
    y0, y1 = float(margin), float(height - margin - (gcfg.GRAPH_LABEL_FONT_PX * 3 if isolated else 0))

    G = nx.Graph()
    G.add_nodes_from(nid for nid in ids if adj[nid])
    for e in graph.edges:
        G.add_edge(e.src, e.dst)
    comps = sorted((sorted(c) for c in nx.connected_components(G)), key=lambda c: (-len(c), c[0]))
    if comps:
        cells = [(math.sqrt(len(c)), _unit_layout(nx, G.subgraph(c), c)) for c in comps]
        row_limit = max(max(s for s, _ in cells),
                        sum(s for s, _ in cells) / math.ceil(math.sqrt(len(cells))))
        rows: list[list] = []
        cur: list = []
        cur_w = 0.0
        for side, local in cells:
            if cur and cur_w + side > row_limit:
                rows.append(cur)
                cur, cur_w = [], 0.0
            cur.append((side, local))
            cur_w += side
        if cur:
            rows.append(cur)
        packed: dict[str, tuple[float, float]] = {}
        y = 0.0
        max_w = 0.0
        for row in rows:
            h = max(s for s, _ in row)
            x = 0.0
            for side, local in row:
                for nid, (fx, fy) in local.items():
                    packed[nid] = (x + fx * side, y + (h - side) / 2 + fy * side)
                x += side
            max_w = max(max_w, x)
            y += h
        max_h = y
        for nid, (px, py) in packed.items():
            fx = 0.5 if max_w == 0 else px / max_w
            fy = 0.5 if max_h == 0 else py / max_h
            pos[nid] = (round(x0 + fx * (x1 - x0), 2), round(y0 + fy * (y1 - y0), 2))
    if isolated:
        step = (x1 - x0) / (len(isolated) - 1) if len(isolated) > 1 else 0.0
        row_y = float(height - margin)
        for i, nid in enumerate(isolated):
            pos[nid] = (round(x0 + i * step, 2), row_y)
    return pos


def _edge_segments(graph: Graph, positions: dict) -> list[tuple[float, float, float, float, Edge]]:
    """Centre-to-centre lines; the k-th parallel edge between the same pair is offset
    perpendicular by GRAPH_PARALLEL_OFFSET_PX * ceil(k/2), alternating sides."""
    counts: dict[tuple[str, str], int] = {}
    out = []
    for e in graph.edges:
        key = (min(e.src, e.dst), max(e.src, e.dst))
        k = counts.get(key, 0)
        counts[key] = k + 1
        (x1, y1), (x2, y2) = positions[e.src], positions[e.dst]
        if k:
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            px, py = -dy / length, dx / length
            off = gcfg.GRAPH_PARALLEL_OFFSET_PX * math.ceil(k / 2) * (1 if k % 2 else -1)
            x1, y1, x2, y2 = x1 + px * off, y1 + py * off, x2 + px * off, y2 + py * off
        out.append((x1, y1, x2, y2, e))
    return out


def _legend_lines(graph_name: str) -> list[tuple[str, str, str]]:
    """(kind, key, colour_or_style) rows for the legend block, node types then edge types."""
    lg = legend_for(graph_name)
    rows = [("node", t, c) for t, c in lg["node_types"].items()]
    rows += [("edge", t, s) for t, s in lg["edge_types"].items()]
    return rows


def _rgba(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(round(alpha * 255))


def to_svg(graph: Graph, positions: dict, width: int, height: int, focus: str | None = None) -> str:
    font = gcfg.GRAPH_LABEL_FONT_PX
    r_node, r_focus = gcfg.GRAPH_NODE_RADIUS_PX, gcfg.GRAPH_FOCUS_RADIUS_PX
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>']
    for x1, y1, x2, y2, e in _edge_segments(graph, positions):
        style = EDGE_STYLES.get(e.type, "solid")
        sw = 3 if style == "won" else 1.5
        alpha = FADED_ALPHA if edge_faded(e) else EDGE_ALPHA
        dash = f' stroke-dasharray="{DASH[style][0]} {DASH[style][1]}"' if style in DASH else ""
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{edge_color(e)}" stroke-width="{sw}" stroke-opacity="{alpha}"{dash}/>')
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        alpha = FADED_ALPHA if node_faded(n) else 1.0
        ring = f' stroke="{FOCUS_RING}" stroke-width="3"' if nid == focus else ""
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{PALETTE.get(n.type, LABEL)}" '
                     f'fill-opacity="{alpha}"{ring}/>')
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        parts.append(f'<text x="{x:.1f}" y="{y + r + font + 2:.1f}" text-anchor="middle" '
                     f'font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="{font}" '
                     f'fill="{LABEL}">{escape(n.label)}</text>')
    ly = 10 + font
    for kind, key, value in _legend_lines(graph.name):
        if kind == "node":
            parts.append(f'<circle cx="16" cy="{ly - font / 3:.1f}" r="5" fill="{value}"/>')
            text = key
        else:
            dash = f' stroke-dasharray="{DASH[value][0]} {DASH[value][1]}"' if value in DASH else ""
            colour = FOCUS_RING if value == "won" else EDGE
            parts.append(f'<line x1="8" y1="{ly - font / 3:.1f}" x2="24" y2="{ly - font / 3:.1f}" '
                         f'stroke="{colour}" stroke-width="{3 if value == "won" else 1.5}"{dash}/>')
            text = f"{key} ({value})"
        parts.append(f'<text x="30" y="{ly:.1f}" font-family="-apple-system, Helvetica, Arial, sans-serif" '
                     f'font-size="{font}" fill="{LABEL}">{escape(text)}</text>')
        ly += font + 4
    parts.append("</svg>")
    return "\n".join(parts)


def _png_line(draw, x1, y1, x2, y2, fill, width, style):
    if style not in DASH:
        draw.line([(x1, y1), (x2, y2)], fill=fill, width=width)
        return
    on, off = DASH[style]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    t = 0.0
    while t < length:
        seg = min(on, length - t)
        draw.line([(x1 + ux * t, y1 + uy * t), (x1 + ux * (t + seg), y1 + uy * (t + seg))],
                  fill=fill, width=width)
        t += on + off


def to_png(graph: Graph, positions: dict, width: int, height: int, focus: str | None = None) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font_px = gcfg.GRAPH_LABEL_FONT_PX
    r_node, r_focus = gcfg.GRAPH_NODE_RADIUS_PX, gcfg.GRAPH_FOCUS_RADIUS_PX
    img = Image.new("RGBA", (width, height), _rgba(BG, 1.0))
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default(size=font_px)

    def _txt(s: str) -> str:                     # risk 4: default font is Latin-1-safe
        return s.encode("latin-1", "replace").decode("latin-1")

    for x1, y1, x2, y2, e in _edge_segments(graph, positions):
        style = EDGE_STYLES.get(e.type, "solid")
        alpha = FADED_ALPHA if edge_faded(e) else EDGE_ALPHA
        _png_line(draw, x1, y1, x2, y2, _rgba(edge_color(e), alpha), 3 if style == "won" else 2, style)
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        alpha = FADED_ALPHA if node_faded(n) else 1.0
        if nid == focus:
            draw.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=_rgba(FOCUS_RING, 1.0))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=_rgba(PALETTE.get(n.type, LABEL), alpha))
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        draw.text((x, y + r + 2), _txt(n.label), fill=_rgba(LABEL, 1.0), font=font, anchor="ma")
    ly = 10
    for kind, key, value in _legend_lines(graph.name):
        cy = ly + font_px / 2
        if kind == "node":
            draw.ellipse([11, cy - 5, 21, cy + 5], fill=_rgba(value, 1.0))
            text = key
        else:
            colour = FOCUS_RING if value == "won" else EDGE
            _png_line(draw, 8, cy, 24, cy, _rgba(colour, 1.0), 3 if value == "won" else 2, value)
            text = f"{key} ({value})"
        draw.text((30, ly), _txt(text), fill=_rgba(LABEL, 1.0), font=font)
        ly += font_px + 4
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def error_image_svg(text: str, width: int, height: int) -> str:
    font = gcfg.GRAPH_LABEL_FONT_PX
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>'
            f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
            f'font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="{font}" '
            f'fill="{LABEL}">{escape(text)}</text></svg>')


def error_image_png(text: str, width: int, height: int) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), _rgba(BG, 1.0)[:3])
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=gcfg.GRAPH_LABEL_FONT_PX)
    draw.text((width / 2, height / 2), text.encode("latin-1", "replace").decode("latin-1"),
              fill=_rgba(LABEL, 1.0)[:3], font=font, anchor="mm")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
