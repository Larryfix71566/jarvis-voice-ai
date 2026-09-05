"""MORTIMER_GRAPH_LAYER_PLAN.md §6 — every tuning knob, read ONCE at import.

Other modules read these as `gcfg.NAME` at call time (never `from ... import NAME`)
so tests can monkeypatch `jarvis.graphs.config.NAME`."""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


GRAPH_DEFAULT_DEPTH = _int_env("JARVIS_GRAPH_DEPTH", 2)
GRAPH_MAX_DEPTH = 4
GRAPH_MAX_NODES = _int_env("JARVIS_GRAPH_MAX_NODES", 500)
GRAPH_MEMORY_MAX_FACTS = 5000
GRAPH_EXECUTION_MAX_RUNS = 200
GRAPH_DELIBERATION_MAX_ROUNDS = 100
GRAPH_DEFAULT_SINCE = _str_env("JARVIS_GRAPH_SINCE", "7d")
GRAPH_LABEL_MAX_CHARS = 48
GRAPH_IMAGE_W = 1400
GRAPH_IMAGE_H = 900
GRAPH_IMAGE_MIN_PX = 400
GRAPH_IMAGE_MAX_PX = 3000
GRAPH_MARGIN_PX = 60
GRAPH_LEGEND_W_PX = 170          # left column reserved for the legend block; nodes start right of it
GRAPH_NODE_RADIUS_PX = 9
GRAPH_FOCUS_RADIUS_PX = 14
GRAPH_LABEL_FONT_PX = 12
GRAPH_PARALLEL_OFFSET_PX = 6
GRAPH_LAYOUT_SEED = 42
GRAPH_LAYOUT_K = 1.6
GRAPH_LAYOUT_ITERATIONS = 120
