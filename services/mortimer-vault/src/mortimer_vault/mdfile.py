"""Parse/serialize a markdown file with YAML frontmatter delimited by --- lines (§4)."""
from __future__ import annotations

import yaml

from .schema import FIELD_ORDER

FRONTMATTER_DELIM = "---"


class ParseError(Exception):
    pass


def parse(raw: str) -> tuple[dict, str]:
    """Split raw file text into (frontmatter_dict, body). Raises ParseError if malformed."""
    if not raw.startswith(FRONTMATTER_DELIM):
        raise ParseError("file does not start with '---' frontmatter delimiter")
    lines = raw.split("\n")
    if lines[0].strip() != FRONTMATTER_DELIM:
        raise ParseError("first line is not exactly '---'")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONTMATTER_DELIM:
            end_idx = i
            break
    if end_idx is None:
        raise ParseError("no closing '---' frontmatter delimiter found")

    fm_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    if body.startswith("\n"):
        body = body[1:]

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        raise ParseError(f"invalid YAML frontmatter: {e}") from e

    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise ParseError("frontmatter did not parse to a mapping")

    return fm, body


def serialize(fm: dict, body: str) -> str:
    """Serialize frontmatter (in FIELD_ORDER) + body back to file text. Body stored byte-exact."""
    ordered = {k: fm[k] for k in FIELD_ORDER if k in fm}
    # include any extra keys after the known ones (tolerant round-trip; strict validation
    # happens separately and rejects unknown keys before this is ever called on write path)
    for k in fm:
        if k not in ordered:
            ordered[k] = fm[k]
    fm_text = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{FRONTMATTER_DELIM}\n{fm_text}\n{FRONTMATTER_DELIM}\n{body}"
