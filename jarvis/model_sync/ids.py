"""Model ID parsing and version ordering for the daily new-model check (WS-41).

Pure functions, no I/O. One place decides what "the same family" and
"newer" mean, so the public-source parsers, the subscription lists, the
pin scan and the detector never disagree.

Recognised shapes (anything else parses to None and is ignored):

- Anthropic: ``claude-<family>-<major>[-<minor>][-<YYYYMMDD>]``, e.g.
  ``claude-fable-5-2``, ``claude-sonnet-4-5-20250929``. Family is any
  lowercase word (``opus``, ``sonnet``, ``haiku``, ``fable``, ``mythos`` ...),
  so a new family name still parses. The pre-4 shape
  ``claude-3-7-sonnet-20250219`` parses too (family ``sonnet``).
- OpenAI/Codex: ``gpt-<major>[.<minor>][-<name>]`` with an optional
  trailing ``-codex`` / ``-codex-max`` / ``-mini``-style qualifier, e.g.
  ``gpt-6-astra``, ``gpt-6.2-sol``, ``gpt-5.3-codex``. Family is everything
  after the version (``astra``, ``sol``, ``codex``, ``base`` when absent).
- Moonshot/Kimi: ``kimi-k<major>[.<minor>][-<qualifier>]``, e.g. ``kimi-k3``,
  ``kimi-k2.7-code``, ``kimi-k3.1-pro``. Family is the qualifier or ``base``.

A vendor-qualified ID (``anthropic/claude-opus-5``, ``moonshotai/kimi-k3``)
is parsed on the part after the last ``/``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CLAUDE = re.compile(
    r"claude-(?P<family>[a-z]+)-(?P<major>\d{1,2})(?:-(?P<minor>\d{1,2}))?(?:-(?P<date>\d{8}))?")
_CLAUDE_OLD = re.compile(
    r"claude-(?P<major>\d)(?:-(?P<minor>\d))?-(?P<family>[a-z]+)(?:-(?P<date>\d{8}))?")
_GPT = re.compile(
    r"gpt-(?P<major>\d{1,2})(?:\.(?P<minor>\d{1,2}))?(?:-(?P<family>[a-z]+(?:-[a-z]+)*))?")
_KIMI = re.compile(
    r"kimi-k(?P<major>\d{1,2})(?:\.(?P<minor>\d{1,2}))?(?:-(?P<family>[a-z]+(?:-[a-z]+)*))?")

# For finding IDs inside free text (release notes, config files). Bounded on
# both sides so `claude-opus-5-5` is not read out of `claude-opus-5-5-fast`'s
# middle and `gpt-6.2-sol` is not cut at the dot.
_EDGE_L = r"(?<![\w./-])"
_EDGE_R = r"(?![\w-]|\.\d)"
TEXT_ID = re.compile(
    _EDGE_L + r"(?:"
    r"claude-[a-z]+-\d{1,2}(?:-\d{1,2})?(?:-\d{8})?"
    r"|claude-\d(?:-\d)?-[a-z]+(?:-\d{8})?"
    r"|gpt-\d{1,2}(?:\.\d{1,2})?(?:-[a-z]+(?:-[a-z]+)*)?"
    r"|kimi-k\d{1,2}(?:\.\d{1,2})?(?:-[a-z]+(?:-[a-z]+)*)?"
    r")" + _EDGE_R)

# Words that look like a family in prose ("claude-code-2", "gpt-5-api") but
# are not models. Kept small and explicit; an unknown family is reported,
# never acted on, so a false positive costs one line in a report.
_NOT_FAMILIES = frozenset({"code", "api", "cli", "app", "desktop", "agent", "sdk"})


@dataclass(frozen=True, order=False)
class ModelId:
    """One parsed model ID. ``version`` orders releases within a family."""

    raw: str          # exactly as given (vendor prefix stripped)
    vendor: str       # "anthropic" | "openai" | "moonshot"
    family: str       # e.g. "fable", "sonnet", "astra", "base", "code"
    version: tuple[int, int]
    date: str | None  # YYYYMMDD snapshot suffix, Anthropic only

    @property
    def lineage(self) -> tuple[str, str]:
        """(vendor, family): two IDs compare only within one lineage."""
        return (self.vendor, self.family)

    @property
    def undated(self) -> str:
        """The ID without an 8-digit snapshot date (Anthropic's alias form)."""
        if self.date and self.raw.endswith("-" + self.date):
            return self.raw[: -(len(self.date) + 1)]
        return self.raw


def parse(model: str) -> ModelId | None:
    """Parse one model ID; None when it isn't a recognised shape."""
    if not isinstance(model, str):
        return None
    raw = model.strip().lower().rsplit("/", 1)[-1]
    if not raw:
        return None
    m = _CLAUDE.fullmatch(raw)
    if m and m.group("family") not in _NOT_FAMILIES:
        return ModelId(raw, "anthropic", m.group("family"),
                       (int(m.group("major")), int(m.group("minor") or 0)), m.group("date"))
    m = _CLAUDE_OLD.fullmatch(raw)
    if m and m.group("family") not in _NOT_FAMILIES:
        return ModelId(raw, "anthropic", m.group("family"),
                       (int(m.group("major")), int(m.group("minor") or 0)), m.group("date"))
    m = _GPT.fullmatch(raw)
    if m:
        family = m.group("family") or "base"
        if family.split("-", 1)[0] in _NOT_FAMILIES:
            return None
        return ModelId(raw, "openai", family,
                       (int(m.group("major")), int(m.group("minor") or 0)), None)
    m = _KIMI.fullmatch(raw)
    if m:
        return ModelId(raw, "moonshot", m.group("family") or "base",
                       (int(m.group("major")), int(m.group("minor") or 0)), None)
    return None


def find_ids(text: str) -> list[str]:
    """Every recognised model ID mentioned in ``text``, deduplicated, in
    first-seen order, lowercased."""
    seen: dict[str, None] = {}
    for hit in TEXT_ID.findall(text or ""):
        hit = hit.lower()
        if parse(hit) is not None:
            seen.setdefault(hit, None)
    return list(seen)


def is_newer(candidate: str, than: str) -> bool:
    """True when ``candidate`` is a later release in the same lineage as
    ``than``. Different lineages, unparseable IDs or a mere dated snapshot
    of the same version are never newer."""
    a, b = parse(candidate), parse(than)
    if a is None or b is None or a.lineage != b.lineage:
        return False
    return a.version > b.version


def newest(models: list[str] | tuple[str, ...] | set[str]) -> dict[tuple[str, str], str]:
    """Lineage -> the newest ID seen for it. On a version tie the undated
    ID wins (it is what config should pin), then the lexically smallest."""
    best: dict[tuple[str, str], ModelId] = {}
    for model in models:
        mid = parse(model)
        if mid is None:
            continue
        cur = best.get(mid.lineage)
        if cur is None or _rank(mid) > _rank(cur):
            best[mid.lineage] = mid
    return {lineage: mid.raw for lineage, mid in best.items()}


def _rank(mid: ModelId) -> tuple[tuple[int, int], int, str]:
    # Higher is better: version, then undated over dated, then reverse-lexical
    # so the comparison is total and deterministic.
    return (mid.version, 0 if mid.date else 1, "".join(chr(255 - ord(c)) for c in mid.raw))


def same_model(a: str, b: str) -> bool:
    """True when two IDs name one model: equal, or one is the other's
    dated snapshot (``claude-sonnet-4-5`` and ``claude-sonnet-4-5-20250929``),
    which is how Anthropic's deprecation notes treat them."""
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return a.strip().lower() == b.strip().lower()
    if pa.raw == pb.raw:
        return True
    if pa.lineage != pb.lineage or pa.version != pb.version:
        return False
    return pa.undated == pb.undated and (pa.date is None or pb.date is None)
