"""Workflows — K4 of MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md.

A workflow is **prescriptive**: how Larry wants a kind of task done, and
what "done" looks like. It is the fourth knowledge layer, and the one
that did not exist before — memory says what is true, procedures say what
worked before, skills say how to do a thing, workflows say how it SHOULD
be done.

The distinction from procedures is trust, not content:

    procedure   learned from a successful run; evidence; earns standing
                through success counters; explicitly a hint
    workflow    authored by Larry; normative; binding from the moment it
                is written; carries acceptance criteria

Three constraints, all from the plan and all enforced by construction:

1. **Authored, never learned.** Nothing in this module creates a workflow
   from a run. Auto-creation is what `jarvis/procedures.py` is for, and
   mixing the two would make an unreviewed guess look like a rule.

2. **Guidance, not a state machine.** A matched workflow is injected as
   one system message. There is deliberately no executor: nothing here
   runs steps, checks them off, or blocks on them. A workflow executor is
   explicitly out of scope, and building one accidentally is the failure
   mode this docstring exists to prevent.

3. **Explicit before clever.** Matching is token overlap against the
   `when:` text, reusing `jarvis.procedures`'s scorer — one
   implementation, not a second one. No embeddings.

`done_when` is what makes a workflow more than a note: it gives the agent
a concrete self-check before claiming completion, and gives Larry
something specific to point at when work comes back wrong.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from jarvis.procedures import _overlap_score, _tokens

logger = logging.getLogger(__name__)

# Workflows are config, not data: they are authored, reviewed and version
# controlled like the routing table, not accumulated like facts.
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "config" / "workflows"

# A workflow must clearly relate to the task before it is injected. Higher
# than the procedure threshold on purpose: a procedure is a hint that
# costs little when wrong, a workflow asserts a rule and a false match
# tells an agent to follow a policy that does not apply.
MATCH_THRESHOLD = 0.35

# One workflow per run. Two competing policies in one prompt is how an
# agent gets stuck choosing between them; if two match, the stronger wins.
MAX_INJECTED = 1


@dataclass
class Workflow:
    """One authored rule. `source` is kept so a surprising injection can
    be traced back to the file that caused it without guessing."""

    name: str
    when: str
    steps: list[str] = field(default_factory=list)
    done_when: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    source: str = ""
    # MORTIMER_VOICE_WORKFLOWS_PLAN.md D1/D4 — read only by
    # jarvis/voice_workflows.py; the specialist matcher above ignores both.
    triggers: dict[str, list[str]] = field(default_factory=dict)
    priority: int = 100
    # MORTIMER_WORKFLOW_VIEWER_PLAN.md D-V1 (Larry 2026-09-25): an unreviewed
    # draft is listed (the viewer, the knowledge overview) but never matched.
    draft: bool = False

    def as_prompt(self) -> str:
        """Render as guidance. Wording matters: this is stated as the
        user's standing instruction, not as a fact, so an agent that
        cannot follow it says so rather than pretending it did."""
        lines = [f"Larry's standing instruction for this kind of task ({self.name}):"]
        for s in self.steps:
            lines.append(f"- {s}")
        if self.done_when:
            lines.append("It is not done until:")
            for d in self.done_when:
                lines.append(f"- {d}")
        lines.append(
            "Follow this unless Larry says otherwise in this conversation. "
            "If you cannot, say so plainly rather than reporting success."
        )
        return "\n".join(lines)


def workflows_enabled() -> bool:
    """Kill switch, checked at the single load point below."""
    return os.environ.get("JARVIS_WORKFLOWS_ENABLED", "").strip().lower() not in (
        "false", "0", "no",
    )


def _coerce_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if str(v).strip()]


def parse_workflow(data: dict, source: str = "") -> Workflow | None:
    """Build a Workflow from parsed YAML. Returns None (never raises) if
    the required fields are missing — a malformed file must not take the
    voice loop down with it."""
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    when = str(data.get("when") or "").strip()
    if not name or not when:
        return None
    return Workflow(
        name=name,
        when=when,
        steps=_coerce_list(data.get("steps")),
        done_when=_coerce_list(data.get("done_when")),
        agents=[a.lower() for a in _coerce_list(data.get("agents"))],
        source=source,
        triggers=_coerce_triggers(data.get("triggers")),
        priority=_coerce_priority(data.get("priority")),
        draft=data.get("draft") is True,
    )


def _coerce_triggers(value) -> dict[str, list[str]]:
    """MORTIMER_VOICE_WORKFLOWS_PLAN.md D3 — {user, result, reply} lists.
    Unknown keys are dropped; a non-dict is treated as no triggers."""
    if not isinstance(value, dict):
        return {}
    return {
        key: _coerce_list(value.get(key))
        for key in ("user", "result", "reply")
        if value.get(key) is not None
    }


def _coerce_priority(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 100


def load_workflows(directory: Path | None = None) -> list[Workflow]:
    """Read every workflow file. Never raises: a bad file is logged and
    skipped, because one unparseable rule must not disable the rest."""
    if not workflows_enabled():
        return []
    directory = directory or WORKFLOWS_DIR
    if not directory.exists():
        return []
    try:
        import yaml
    except ImportError:
        logger.warning("workflows_skipped reason=pyyaml_missing")
        return []

    out: list[Workflow] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("workflow_parse_failed path=%s", path)
            continue
        wf = parse_workflow(data, source=path.name)
        if wf is None:
            logger.warning("workflow_invalid path=%s reason=missing_name_or_when", path)
            continue
        out.append(wf)
    return out


def match_workflow(
    agent: str,
    task: str,
    workflows: list[Workflow] | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> Workflow | None:
    """The workflow that applies to this task, or None.

    Pure when `workflows` is supplied — that is the test seam. An agent
    list on the workflow restricts it; an empty list means every agent.
    """
    candidates = load_workflows() if workflows is None else workflows
    if not candidates:
        return None

    task_tokens = _tokens(task)
    if not task_tokens:
        return None

    agent_l = (agent or "").lower()
    best: tuple[float, Workflow] | None = None
    for wf in candidates:
        if wf.draft:
            continue   # D-V1: listed, never matched
        if wf.agents and agent_l not in wf.agents:
            continue
        score = _overlap_score(_tokens(wf.when), task_tokens)
        if score < threshold:
            continue
        if best is None or score > best[0]:
            best = (score, wf)
    return best[1] if best else None
