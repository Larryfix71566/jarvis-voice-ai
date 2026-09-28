"""Skills — K3 of MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md.

Larry, 2026-08-18: *"I want our implementation of Skills to mirror what
Claude does for skills so that we could leverage that repository as
well"* and *"skills should only be added one at a time so the risk can
be reviewed individually."*

A skill is **capability knowledge**: how to do a kind of thing, written
down once and reusable. It is the third knowledge layer, and it is
deliberately the only one that speaks a FOREIGN format — the Agent
Skills open standard (agentskills.io, open since 2025-12-18): a folder
containing `SKILL.md`, YAML frontmatter plus a Markdown body, with
optional `scripts/`, `references/` and `assets/` siblings. Mortimer
consumes that format rather than inventing a parallel one, so a
community skill can be dropped in unchanged.

How this differs from its neighbours, since all four layers are text
injected into a prompt and the distinction is easy to lose:

    memory      what is true about Larry and his world
    procedure   what worked before — LEARNED, earns standing through
                success counters, explicitly a hint
    skill       how to do a kind of thing — AUTHORED (or imported),
                assumed correct, no counters
    workflow    how Larry REQUIRES a kind of thing be done, with
                acceptance criteria

Two safety properties hold by construction, not by policy:

1. **Presence on disk is not enough.** A skill loads only if its name is
   listed in `config/skills.yaml`. Cloning a repository of a hundred
   community skills into `skills/` therefore enables exactly zero of
   them — each one has to be named by hand after Larry has read it.
   That is his "one at a time so the risk can be reviewed individually"
   rule, enforced by a data structure rather than by discipline.

2. **There is no execution path in this module.** `scripts/` is the real
   risk in the standard — importing a community skill and running its
   code is arbitrary code execution from the internet on Larry's
   machine. Nothing here runs, imports, or shells out to anything: a
   skill contributes TEXT to a prompt and nothing else. A bundled
   `scripts/` directory is detected and reported loudly (so an operator
   knows the skill expects capabilities it will not get here), never
   invoked. `test_no_execution_path` fails if that ever changes.

Progressive disclosure is the reason the standard fits Mortimer
specifically. The Supervisor runs on a small model with a prompt already
carrying memory context and addenda; a layer that costs ~100 tokens per
skill until something activates it is the right shape. Here that means
`SkillCard` (name + description, cheap) is what matching sees. The legacy
matcher reads one body; the opt-in v2 selector may read one primary and at most
one mutually compatible supporting body.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from jarvis.procedures import _overlap_score, _tokens

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Skills live at the repo root, not under `jarvis/`, because they are
# content rather than code — and because `jarvis/skills/` already means
# the MCP server registry in this codebase. Naming discipline: in code
# and docs an "MCP skill server" is a server; these are skills.
SKILLS_DIR = _REPO_ROOT / "skills"

# The registration gate. A YAML file with one key, `enabled:`, listing
# skill names. Config, not data — reviewed in a diff like the routing
# table and the self-edit allowlist.
SKILLS_CONFIG = _REPO_ROOT / "config" / "skills.yaml"

# Matching is token overlap against name + description, reusing
# jarvis.procedures's scorer — one implementation, not a second one.
# Between a procedure's threshold (a cheap hint) and a workflow's (a
# binding rule): a wrong skill wastes body tokens and misdirects, but
# does not assert a policy that does not apply.
MATCH_THRESHOLD = 0.30

# Legacy matcher limit: one skill per run, same reason MAX_INJECTED is 1 for
# workflows. The opt-in v2 selector has a separate mutual-compatibility gate
# for its optional support skill; it does not change this legacy constant.
MAX_INJECTED = 1

# A single coincidental word is not a match. `_overlap_score` divides by
# the SMALLER token set, so a short task whose one or two tokens both
# appear somewhere in a long description scores 1.0 — measured
# 2026-08-18: "what's the plan for today" tokenizes to {plan, today} and
# scored 0.500 against `technical-plan-document` on the word "plan"
# alone, well above the 0.30 threshold.
#
# Requiring two shared tokens targets that cause directly. Same constant,
# same value, same reasoning as jarvis/consolidate.py's MIN_SHARED_TOKENS
# — one idea, applied twice, not two ideas.
#
# This is why an anti-trigger belongs in the BODY, never the description:
# naming the false-positive phrases in the description adds their exact
# words to the matchable token set. Measured on the same day, adding
# "what are you planning to do next" to this skill's description moved
# that task's score from 0.000 to 1.000 — precisely backwards.
MIN_SHARED_TOKENS = 2
SKILLS_WORKSPACE_ENABLED_ENV = "JARVIS_SKILLS_WORKSPACE_ENABLED"
SKILLS_SELECTION_V2_ENABLED_ENV = "JARVIS_SKILLS_SELECTION_V2"
_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")

# Limits from the standard itself.
NAME_MAX_CHARS = 64
DESCRIPTION_MAX_CHARS = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# The standard reserves these vendor words in skill names.
RESERVED_WORDS = ("anthropic", "claude")
# ~5k tokens, the standard's guidance for a body, measured in chars
# because there is no tokenizer in this path and a rough ceiling is the
# point. Exceeding it is a warning, never a refusal — a long skill from
# the community should still load, loudly.
BODY_SOFT_MAX_CHARS = 20_000


@dataclass
class Skill:
    """One skill. `body` is None until it is actually needed — that
    laziness IS the progressive disclosure, not a micro-optimisation."""

    name: str
    description: str
    path: Path
    metadata: dict = field(default_factory=dict)
    has_scripts: bool = False
    _body: str | None = None

    @property
    def card(self) -> str:
        """Tier one: what matching sees and what a roster line costs."""
        return f"{self.name}: {self.description}"

    def body(self) -> str:
        """Tier two: the Markdown body, read from disk on activation."""
        if self._body is None:
            self._body = _split_frontmatter(
                self.path.read_text(encoding="utf-8"))[1].strip()
        return self._body

    def as_prompt(self) -> str:
        """Render for injection. Stated as reference material, not as an
        order: a skill says how a thing is done, a workflow says it must
        be. An agent that finds it inapplicable should ignore it, and
        saying so is better than forcing a fit."""
        header = (
            f"Reference — skill '{self.name}': {self.description}\n"
            "Use it if it fits this task; ignore it if it does not."
        )
        if self.has_scripts:
            header += (
                "\nThis skill bundles scripts, which Mortimer does not run. "
                "Treat any script it references as unavailable."
            )
        return f"{header}\n\n{self.body()}"


def skills_enabled() -> bool:
    """Kill switch, checked at the single load point below.

    Named JARVIS_AGENT_SKILLS_ENABLED, not JARVIS_SKILLS_ENABLED, because
    "skills" already means MCP servers in this codebase's environment
    vocabulary and a reader must not have to guess which one a variable
    turns off.
    """
    return os.environ.get(
        "JARVIS_AGENT_SKILLS_ENABLED", "").strip().lower() not in ("false", "0", "no")


def skills_workspace_enabled() -> bool:
    """The digest-pinned v2 loader is an explicit opt-in during rollout."""
    return os.environ.get(SKILLS_WORKSPACE_ENABLED_ENV, "").strip() == "1"


def skill_selection_v2_enabled() -> bool:
    """The capability-aware selector is a separate explicit rollout gate."""
    return os.environ.get(SKILLS_SELECTION_V2_ENABLED_ENV, "").strip() == "1"


def read_skill_registry(
    config_path: Path | None = None,
) -> tuple[list[str], dict[str, str] | None, int | None, bool]:
    """Read a legacy or strict schema-v2 registry; malformed v2 fails closed."""
    path = config_path or SKILLS_CONFIG
    if not path.exists():
        return [], None, None, False
    try:
        import yaml

        class UniqueKeyLoader(yaml.SafeLoader):
            """Reject ambiguous YAML mappings instead of silently taking the last key."""

        def construct_unique_mapping(loader, node, deep=False):
            loader.flatten_mapping(node)
            mapping = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in mapping
                except TypeError:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        "found an unhashable mapping key", key_node.start_mark,
                    ) from None
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        "found a duplicate mapping key", key_node.start_mark,
                    )
                mapping[key] = loader.construct_object(value_node, deep=deep)
            return mapping

        UniqueKeyLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping,
        )
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader) or {}
    except Exception as exc:  # noqa: BLE001 — never log content or path
        logger.warning("skills_config_unreadable error_type=%s", type(exc).__name__[:80])
        return [], None, None, False
    if not isinstance(data, dict):
        return [], None, None, False

    version = data.get("schema_version")
    if version is None:
        raw_names = data.get("enabled") or []
        if isinstance(raw_names, (str, bytes)):
            return [], None, None, False
        try:
            names = [str(name).strip() for name in raw_names if str(name).strip()]
        except TypeError:
            return [], None, None, False
        return names, None, None, True

    if version != 2 or set(data) != {"schema_version", "enabled", "revisions"}:
        return [], None, version if isinstance(version, int) else None, False
    names = data.get("enabled")
    pins = data.get("revisions")
    if (not isinstance(names, list) or not isinstance(pins, dict)
            or any(not isinstance(name, str) or not NAME_RE.fullmatch(name) for name in names)
            or len(names) != len(set(names))
            or set(pins) != set(names)
            or any(not isinstance(name, str) or not NAME_RE.fullmatch(name)
                   or not isinstance(digest, str) or not _REVISION_RE.fullmatch(digest)
                   for name, digest in pins.items())):
        return [], None, 2, False
    return list(names), dict(pins), 2, True


def skill_revision_pins(config_path: Path | None = None) -> dict[str, str] | None:
    """Return digest pins only for a structurally valid v2 registry."""
    _names, pins, version, valid = read_skill_registry(config_path)
    return pins if valid and version == 2 else None


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Missing frontmatter yields ("", text)
    so a malformed file fails validation rather than raising."""
    # Delimiters are whole lines. Splitting on ``\n---`` also matches a
    # Markdown horizontal rule or a unified-diff header in the body and
    # silently discards everything after it. Retain line endings exactly;
    # SKILL.md content is prompt material and must not be truncated here.
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return "", text
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:])
    return "", text


def validate_frontmatter(data: dict) -> list[str]:
    """Every reason this frontmatter is not a valid skill, as plain
    sentences. Pure. An empty list means valid.

    Returns ALL problems rather than the first — someone fixing an
    imported skill should see the whole list in one pass.
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["frontmatter is not a YAML mapping"]

    name = str(data.get("name") or "").strip()
    description = str(data.get("description") or "").strip()

    if not name:
        problems.append("missing required field: name")
    else:
        if len(name) > NAME_MAX_CHARS:
            problems.append(f"name is {len(name)} chars (max {NAME_MAX_CHARS})")
        if not NAME_RE.match(name):
            problems.append(
                f"name {name!r} must be lowercase letters, digits and single hyphens")
        for word in RESERVED_WORDS:
            if word in name.lower():
                problems.append(f"name may not contain the reserved word {word!r}")
        if "<" in name or ">" in name:
            problems.append("name may not contain XML tags")

    if not description:
        problems.append("missing required field: description")
    elif len(description) > DESCRIPTION_MAX_CHARS:
        problems.append(
            f"description is {len(description)} chars (max {DESCRIPTION_MAX_CHARS})")

    return problems


def parse_skill(path: Path) -> tuple[Skill | None, list[str]]:
    """Read one SKILL.md. Returns (skill, problems); never raises.

    A skill that fails validation is not silently dropped — the problems
    come back so the loader can log them and `--validate` can print them.
    """
    try:
        # Disable universal-newline conversion so the parser can retain the
        # package's exact body bytes when it snapshots instruction content.
        with path.open("r", encoding="utf-8", newline="") as source:
            text = source.read()
    except OSError as exc:
        return None, [f"unreadable: {exc}"]

    front, body = _split_frontmatter(text)
    if not front.strip():
        return None, ["no YAML frontmatter (a SKILL.md must start with ---)"]

    try:
        import yaml
    except ImportError:  # pragma: no cover - pyyaml is a hard dependency
        return None, ["pyyaml is not installed"]

    try:
        data = yaml.safe_load(front)
    except Exception as exc:  # noqa: BLE001
        return None, [f"frontmatter is not valid YAML: {exc}"]

    problems = validate_frontmatter(data)
    if problems:
        return None, problems

    if len(body) > BODY_SOFT_MAX_CHARS:
        problems.append(
            f"body is {len(body)} chars, above the ~{BODY_SOFT_MAX_CHARS} guidance "
            "— it will still load, but progressive disclosure stops paying off")

    metadata = data.get("metadata")
    skill = Skill(
        name=str(data["name"]).strip(),
        description=str(data["description"]).strip(),
        path=path,
        metadata=metadata if isinstance(metadata, dict) else {},
        has_scripts=(path.parent / "scripts").is_dir(),
        _body=body.strip(),
    )
    return skill, problems


def enabled_names(config_path: Path | None = None) -> list[str]:
    """The registration gate. Names listed in config/skills.yaml.

    A missing config file means NO skills are enabled — the safe
    direction. A skill that exists on disk but is not named here is
    inert, which is the whole point of the file.
    """
    names, _pins, _version, valid = read_skill_registry(config_path)
    return names if valid else []


def discover(directory: Path | None = None) -> list[tuple[Path, Skill | None, list[str]]]:
    """Every SKILL.md under `directory`, parsed, regardless of whether it
    is enabled. This is what `--validate` and `--list` read; the runtime
    loader below filters this down."""
    directory = directory or SKILLS_DIR
    if not directory.exists():
        return []
    out = []
    for path in sorted(directory.glob("*/SKILL.md")):
        skill, problems = parse_skill(path)
        out.append((path, skill, problems))
    return out


def load_skills(
    directory: Path | None = None,
    config_path: Path | None = None,
) -> list[Skill]:
    """The runtime set: parsed, valid, AND registered in config.

    Never raises — a broken skill is logged and skipped, because one bad
    import must not disable the rest or take a run down.
    """
    if not skills_enabled():
        return []
    allowed = set(enabled_names(config_path))
    if not allowed:
        return []

    revision_map: dict[str, str] | None = None
    if skills_workspace_enabled():
        names, revision_map, version, valid = read_skill_registry(config_path)
        if not valid or version != 2 or not revision_map:
            logger.warning("skill_workspace_registry_unavailable")
            return []
        allowed = set(names)

    out: list[Skill] = []
    for path, skill, problems in discover(directory):
        if skill is None:
            logger.warning("skill_invalid problem_count=%d", len(problems))
            continue
        if skill.name not in allowed:
            # Not an error: the normal state of an unreviewed skill.
            logger.debug("skill_not_enabled")
            continue
        if revision_map is not None:
            try:
                from jarvis.skill_catalog import inspect_package

                package = inspect_package(path.parent, config_path=config_path)
                if package.revision != revision_map.get(skill.name):
                    logger.warning("skill_revision_pin_refused")
                    continue
            except Exception as exc:  # noqa: BLE001 — one broken package is isolated
                logger.warning("skill_revision_check_failed error_type=%s",
                               type(exc).__name__[:64])
                continue
        for p in problems:
            logger.warning("skill_warning")
        if skill.has_scripts:
            logger.warning("skill_bundles_scripts — scripts are NEVER executed")
        out.append(skill)
    return out


def match_skill(
    task: str,
    skills: list[Skill] | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> Skill | None:
    """The skill that applies to this task, or None.

    Pure when `skills` is supplied — that is the test seam. Matching
    reads the CARD only (name + description), never the body: that is
    what makes tier one cheap.
    """
    candidates = load_skills() if skills is None else skills
    if not candidates:
        return None
    task_tokens = _tokens(task)
    if not task_tokens:
        return None

    best: tuple[float, Skill] | None = None
    for skill in candidates:
        card_tokens = _tokens(skill.card)
        score = _overlap_score(card_tokens, task_tokens)
        if score < threshold:
            continue
        if len(card_tokens & task_tokens) < MIN_SHARED_TOKENS:
            continue
        if best is None or score > best[0]:
            best = (score, skill)
    return best[1] if best else None


# --- authoring -------------------------------------------------------------


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:NAME_MAX_CHARS].strip("-") or "skill"


def write_skill(
    name: str,
    description: str,
    body: str,
    metadata: dict | None = None,
    directory: Path | None = None,
) -> Path:
    """Write one SKILL.md. Refuses to overwrite.

    Deliberately does NOT touch config/skills.yaml: writing the file and
    enabling it are two decisions, and the second one is Larry's. A
    freshly written skill is inert until he adds its name by hand.
    """
    directory = directory or SKILLS_DIR
    problems = validate_frontmatter({"name": name, "description": description})
    if problems:
        raise ValueError("; ".join(problems))

    folder = directory / name
    path = folder / "SKILL.md"
    if path.exists():
        raise FileExistsError(str(path))
    folder.mkdir(parents=True, exist_ok=True)

    lines = ["---", f"name: {name}", f"description: {description}"]
    if metadata:
        lines.append("metadata:")
        for k, v in metadata.items():
            lines.append(f"  {k}: {v}")
    lines += ["---", "", body.rstrip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def skill_from_procedure(row: dict, directory: Path | None = None) -> Path:
    """Promote one learned procedure into an authored skill.

    This is the intended path from the evidential layer to the
    capability layer, and it is one-way in exactly one sense: a skill
    carries no success/failure counters, so promotion trades the safety
    net for assumed-correct status. The procedure ROW IS KEPT — its
    counters keep updating and it keeps being matched — because
    promotion is a copy, not a move, and an over-eager promotion should
    be undone by removing a name from config/skills.yaml rather than by
    reconstructing a deleted row.
    """
    name = _slug(row.get("label") or "")
    description = str(row.get("description") or "").strip()
    if len(description) > DESCRIPTION_MAX_CHARS:
        description = description[: DESCRIPTION_MAX_CHARS - 1].rstrip() + "…"

    agent = str(row.get("agent") or "")
    ok = int(row.get("success_count") or 0)
    bad = int(row.get("failure_count") or 0)
    body = (
        f"# {row.get('label') or name}\n\n"
        "## When to use this\n\n"
        f"{description}\n\n"
        "## Steps\n\n"
        "REVIEW ME — this body was generated from a learned procedure's "
        "one-line summary. Replace this section with the actual steps "
        "before relying on it; the frontmatter above is what makes the "
        "skill discoverable, and this body is what makes it useful.\n\n"
        "## Provenance\n\n"
        f"- Promoted from procedure #{row.get('id')} (`{agent}` agent).\n"
        f"- Evidence at promotion: {ok} success(es), {bad} failure(s).\n"
        "- The procedure row is kept and keeps accruing counters; this "
        "skill does not.\n"
    )
    return write_skill(
        name=name,
        description=description or f"Procedure promoted from the {agent} agent.",
        body=body,
        metadata={
            "source": f"procedure:{row.get('id')}",
            "agent": agent,
            "promoted_successes": ok,
            "promoted_failures": bad,
        },
        directory=directory,
    )


# --- CLI -------------------------------------------------------------------


def explain(
    task: str,
    directory: Path | None = None,
    config_path: Path | None = None,
) -> str:
    """Part A — score every skill on disk against `task` and show the work.

    Mirrors `jarvis.procedures._explain` (D23) deliberately: same purpose,
    same shape, one convention. Without it, "does this skill match the
    right tasks?" can only be answered by restarting the bot and running a
    live delegation, which gives a yes/no and no score to reason about.

    Deliberately DB-free — skills are files, not rows, so this works on a
    fresh checkout with no database.

    This is also the enable gate (D2a): a skill is not registered in
    config/skills.yaml without recorded scores for two tasks it should
    match and two it must not. The negative cases are the ones that
    matter — MAX_INJECTED is 1, so an over-matching skill does not merely
    add noise, it displaces the skill that should have won.
    """
    found = discover(directory)
    allowed = set(enabled_names(config_path))
    task_tokens = _tokens(task)

    out = [
        f"task: {task!r}",
        f"task tokens ({len(task_tokens)}): {sorted(task_tokens)}",
        f"threshold: {MATCH_THRESHOLD}",
        "",
    ]
    if not found:
        out.append(f"no skills found under {directory or SKILLS_DIR}")
        return "\n".join(out)
    if not task_tokens:
        out.append("no scorable tokens in the task — nothing can match")
        return "\n".join(out)

    scored: list[tuple[float, Skill, set[str]]] = []
    for path, skill, _problems in found:
        if skill is None:
            out.append(f"[ INVALID ] {path.parent.name} — cannot be scored")
            continue
        card_tokens = _tokens(skill.card)
        scored.append((_overlap_score(card_tokens, task_tokens), skill,
                       card_tokens & task_tokens))

    scored.sort(key=lambda t: t[0], reverse=True)

    def qualifies(score: float, shared: set[str]) -> bool:
        return score >= MATCH_THRESHOLD and len(shared) >= MIN_SHARED_TOKENS

    # Only an ENABLED, qualifying skill can be injected, and only the top
    # one of those — exactly what match_skill returns.
    winner = next(
        (s for score, s, shared in scored
         if qualifies(score, shared) and s.name in allowed), None)

    for score, skill, shared in scored:
        state = "enabled" if skill.name in allowed else "inert  "
        ok = qualifies(score, shared)
        mark = "<< INJECTED" if skill is winner else ""
        out.append(
            f"[{state}] score={score:.3f} {'PASS' if ok else 'fail':<4} "
            f"{skill.name} {mark}".rstrip()
        )
        out.append(f"          shared_tokens={sorted(shared)}")
        if score >= MATCH_THRESHOLD and len(shared) < MIN_SHARED_TOKENS:
            out.append(
                f"          (above threshold but only {len(shared)} shared "
                f"token — needs {MIN_SHARED_TOKENS}; a single coincidental "
                "word is not a match)")

    out.append("")
    if winner is None:
        above = [s.name for sc, s, sh in scored if qualifies(sc, sh)]
        if above:
            out.append(
                "Nothing would be injected: the skills above threshold "
                f"({', '.join(above)}) are inert. Enable one in "
                f"{(config_path or SKILLS_CONFIG).name} to use it.")
        else:
            out.append("Nothing would be injected — no skill reached the threshold.")
    else:
        out.append(f"Would inject: {winner.name}")
        others = [s.name for sc, s, sh in scored
                  if qualifies(sc, sh) and s is not winner]
        if others:
            out.append(
                f"Also above threshold but NOT injected (MAX_INJECTED={MAX_INJECTED}): "
                f"{', '.join(others)}. If one of those should have won, the two "
                "descriptions overlap — merge or sharpen them rather than "
                "shipping competitors.")
    return "\n".join(out)


def format_inventory(directory: Path | None = None,
                     config_path: Path | None = None) -> str:
    """What is on disk, what is enabled, and what is wrong with the rest."""
    found = discover(directory)
    if not found:
        return f"No skills found under {directory or SKILLS_DIR}."
    allowed_list, pins, version, registry_valid = read_skill_registry(config_path)
    allowed = set(allowed_list if registry_valid else [])

    out = [f"{len(found)} skill folder(s); {len(allowed)} enabled in "
           f"{(config_path or SKILLS_CONFIG).name}.\n"]
    if not registry_valid:
        out.append("  registry: INVALID — no skills are enabled")
    elif version == 2:
        out.append(
            "  registry: schema v2; digest enforcement "
            f"{'ON' if skills_workspace_enabled() else 'OFF (legacy loader)'}"
        )
    else:
        out.append("  registry: legacy, package digests are not pinned")
    for path, skill, problems in found:
        if skill is None:
            out.append(f"  [INVALID]  {path.parent.name}")
            for p in problems:
                out.append(f"             {p}")
            continue
        state = "enabled " if skill.name in allowed else "inert   "
        out.append(f"  [{state}] {skill.name}")
        out.append(f"             {skill.description[:96]}")
        if version == 2 and registry_valid:
            if skill.name not in allowed:
                # The v2 registry pins enabled packages only. An unregistered
                # folder is an intentional inert candidate, not a pin failure.
                pin_state = "not configured (inert)"
            else:
                try:
                    from jarvis.skill_catalog import inspect_package

                    actual = inspect_package(path.parent, config_path=config_path).revision
                    pin_state = "matches" if pins and pins.get(skill.name) == actual else "MISMATCH"
                except Exception:  # noqa: BLE001 — CLI reports state, never package content
                    pin_state = "unavailable"
            out.append(f"             digest pin: {pin_state}")
        elif registry_valid:
            out.append("             digest pin: not configured")
        if skill.has_scripts:
            out.append("             bundles scripts/ — NEVER executed by Mortimer")
        for p in problems:
            out.append(f"             warning: {p}")
    out.append("")
    out.append("A skill on disk does nothing until its name is listed under")
    out.append(f"`enabled:` in {(config_path or SKILLS_CONFIG)} — one at a time,")
    out.append("each reviewed on its own.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="python -m jarvis.agent_skills")
    p.add_argument("--list", action="store_true",
                   help="show every skill on disk and whether it is enabled")
    p.add_argument("--validate", action="store_true",
                   help="exit non-zero if any skill package, metadata, or active digest pin is invalid")
    p.add_argument("--from-procedure", metavar="ID", type=int,
                   help="write a SKILL.md draft from one procedure (kept, not moved)")
    p.add_argument("--force", action="store_true",
                   help="allow --from-procedure on a non-active procedure")
    p.add_argument("--explain", metavar="TASK",
                   help="score every skill against a task and show which "
                        "would be injected")
    args = p.parse_args(argv)

    if args.explain:
        print(explain(args.explain))
        return 0

    if args.from_procedure is not None:
        from jarvis.db import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM procedures WHERE id = ?", (args.from_procedure,)
            ).fetchone()
        if row is None:
            print(f"no procedure with id {args.from_procedure}")
            return 1
        row = dict(row)
        if row.get("status") != "active" and not args.force:
            print(f"procedure #{row['id']} is '{row.get('status')}', not 'active'.")
            print("Only a procedure that has earned promotion should become a "
                  "skill — a candidate has not yet cleared its success "
                  "threshold. Use --force if you mean it.")
            return 1
        try:
            path = skill_from_procedure(row)
        except (ValueError, FileExistsError) as exc:
            print(f"refused: {exc}")
            return 1
        print(f"wrote {path}")
        print("The procedure row is unchanged and still matched.")
        print("This skill is INERT until you add its name to "
              f"{SKILLS_CONFIG} under `enabled:`.")
        return 0

    if args.validate:
        from jarvis.skill_catalog import validate_skill_inventory

        frontmatter_errors = {}
        for path, skill, problems in discover():
            if skill is None:
                frontmatter_errors[path.parent.name] = path
                print(f"INVALID {path}")
                for problem in problems:
                    print(f"        {problem}")
        package_errors = validate_skill_inventory()
        for error in package_errors:
            skill_id = error.partition(":")[0]
            if skill_id in frontmatter_errors and error.endswith("invalid_skill_instructions"):
                continue
            print(f"INVALID {error}")
        if not frontmatter_errors and not package_errors:
            print("All skill packages, metadata, and active digest pins are valid.")
        return 1 if frontmatter_errors or package_errors else 0

    print(format_inventory())
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
