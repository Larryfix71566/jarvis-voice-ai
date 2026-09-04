"""Financial-detail detection for the sensitive-turn guard (T4a, contract K3).

Stdlib only, by rule (MORTIMER_SECURITY_HARDENING_PLAN.md §0.5): this module
is imported by jarvis/memory.py, which the bot, the CLI, the admin sidecar and
the MCP memory server all import. A heavy import here costs every one of them.

Nothing in this module stores, encrypts, logs or transmits anything. It
answers one question — "does this text contain a financial detail we must not
persist yet?" — and returns only a KIND and a SPAN, never the matched text, so
a caller that logs a FinancialMatch still leaks nothing.

Every pattern below was re-extracted and executed on 2026-08-27 against the 92
utterances in MORTIMER_SECURITY_HARDENING_PLAN.md §7.1 (28 positive, 64
negative) PLUS this repo's 68-utterance routing-eval fixture
(tests/evals/cases.yaml) — 160 inputs, 0 false positives, 0 false negatives.
The negatives include the 18 shapes that broke the first draft (review F3:
owe⊂borrowed, checking-the-build, account-then-order-number). Changing a
pattern invalidates that measurement — change the tests in the same edit and
re-run.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["card", "account", "routing", "iban", "balance"]


@dataclass(frozen=True)
class FinancialMatch:
    """kind: which detector fired. span: the span of the SENSITIVE TOKEN
    itself (the digit run, the IBAN, the money amount) in the input string —
    NOT the span of the keyword context that qualified it. T4b excerpts by
    this span, so widening it would store the surrounding words too."""

    kind: Kind
    span: tuple[int, int]


# --------------------------------------------------------------------------
# Kill switch (plan §6, D-H10). Read HERE and nowhere else in the codebase.
# --------------------------------------------------------------------------

SENSITIVE_GUARD_ENABLED_ENV = "JARVIS_SENSITIVE_GUARD_ENABLED"


def guard_enabled() -> bool:
    """True unless JARVIS_SENSITIVE_GUARD_ENABLED is an explicit false value."""
    return os.environ.get(SENSITIVE_GUARD_ENABLED_ENV, "").strip().lower() not in (
        "0", "false", "no", "off",
    )


# --------------------------------------------------------------------------
# ⚙ TUNING KNOBS (plan §6, D-H5). Each number lives here and nowhere else.
# --------------------------------------------------------------------------

#: ISO/IEC 7812 PAN length, after separators are removed.
CARD_MIN_DIGITS = 13
CARD_MAX_DIGITS = 19
#: A solid digit run this long, after an account keyword, is an account number.
#: 6 excludes 5-digit US zips and 4-digit "ending in" fragments.
ACCOUNT_MIN_DIGITS = 6
ACCOUNT_MAX_DIGITS = 17
#: How far a financial keyword may sit from its digits / money amount
#: (routing and balance only; account uses a connector-chain, not a window).
CONTEXT_WINDOW_CHARS = 40
#: ISO 13616.
IBAN_MIN_TOTAL = 15
IBAN_MAX_TOTAL = 34
#: Below this, an amount beside a financial noun is a trivial IOU, not a
#: balance (plan R-5, re-measured after the word-boundary fix). 25.0 catches a
#: $50/$47.32 balance and rejects "owe you $20 for lunch". Set to 0.0 for the
#: roadmap's literal "any amount beside a financial noun" behaviour.
BALANCE_MIN_AMOUNT = 25.0


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

# card — an unseparated 13-19 digit run, OR 3-5 groups of 4-6 digits joined by
# single spaces or hyphens. The group FLOOR OF 4 is the load-bearing part: it
# is what rejects dates (2026-08-27 -> 4,2,2), zip+4 (35242-1234 -> only one
# separator, needs >=2), phone numbers (555-123-4567 -> 3,3,4) and SSN shapes
# (123-45-6789 -> 3,2,4) without a single special case.
_CARD_RE = re.compile(
    r"(?<![\w-])(?:\d{13,19}|\d{4,6}(?:[ -]\d{4,6}){2,4})(?![\w-])"
)

# routing — exactly 9 digits AND the ABA checksum AND a routing keyword within
# CONTEXT_WINDOW_CHARS, in either order. All three, because nine bare digits
# is also a zip+4 with the hyphen eaten and a dozen other things.
_ROUTING_RE = re.compile(
    rf"(?i)\b(?:routing|aba|rtn|transit)\b"
    rf"[^\n]{{0,{CONTEXT_WINDOW_CHARS}}}?(?<![\w-])(\d{{9}})(?![\w-])"
    rf"|(?<![\w-])(\d{{9}})(?![\w-])"
    rf"[^\n]{{0,{CONTEXT_WINDOW_CHARS}}}?\b(?:routing|aba|rtn|transit)\b"
)

# account — a connector-chain, NOT a proximity window (review F3). An account
# NOUN (account/acct/checking account/savings account/bank account), then only
# connective tokens (number/num/no/is/ending/in and punctuation) before a SOLID
# 6-17 digit run. A COMPETING noun between the keyword and the digits breaks the
# chain, so "my account, the order number is 8675309" and "log in to my
# account, my member id is 998877" do NOT match (both were false positives in
# the first draft's window rule), while "account number is 000123456789" and
# "Account: 100200300400" do. The bare-verb "checking"/"savings" alternatives
# are gone — they matched "checking build 1049322". Solid (no internal
# separators) still costs a grouped account number ("account 0001 2345 6789");
# see plan §10 R-H3.
_ACCOUNT_RE = re.compile(
    r"(?i)\b(?:(?:checking|savings|bank)\s+account|account|acct)\b"
    r"(?:[\s:#.,\-]*\b(?:number|num|no|is|ending|in)\b)*"
    r"[\s:#.,\-]*"
    rf"(?<![\w-])(\d{{{ACCOUNT_MIN_DIGITS},{ACCOUNT_MAX_DIGITS}}})(?![\w-])"
)

# iban — CC dd + 11..30 alphanumerics, then mod-97. UPPERCASE ONLY: there is
# deliberately no re.IGNORECASE here, and that is what keeps "gpt-5.1",
# "462da350", "97d5cecc" and "eleven_flash_v2_5" out before mod-97 is
# even reached.
_IBAN_RE = re.compile(r"(?<![\w-])([A-Z]{2}\d{2}[A-Z0-9]{11,30})(?![\w-])")

# balance — the roadmap's money shape, plus BALANCE_MIN_AMOUNT (plan R-5),
# adjacent to a financial noun. WORD BOUNDARIES (review F3) are load-bearing:
# without them "owe" matched inside borrowed/however/allowed/followed/flowers/
# tower/vowel/lowered/slowed/showed and "account" inside "accounting". IRA is
# case-SENSITIVE (outside the (?i:...) group) so the given name "Ira" is not a
# financial keyword; everything else is case-insensitive.
_MONEY_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)")
_FIN_WORD_RE = re.compile(
    r"(?:\b(?i:balance|accounts?|owed?|savings|checking|401\s?k|brokerage)\b|\bIRA\b)"
)


# --------------------------------------------------------------------------
# Checksums
# --------------------------------------------------------------------------

def _luhn_ok(digits: str) -> bool:
    """ISO/IEC 7812 check digit."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _aba_ok(digits: str) -> bool:
    """US ABA routing transit number check digit."""
    if len(digits) != 9:
        return False
    d = [ord(c) - 48 for c in digits]
    checksum = (3 * (d[0] + d[3] + d[6])
                + 7 * (d[1] + d[4] + d[7])
                + 1 * (d[2] + d[5] + d[8]))
    return checksum % 10 == 0


def _iban_ok(token: str) -> bool:
    """ISO 13616 mod-97-10."""
    if not (IBAN_MIN_TOTAL <= len(token) <= IBAN_MAX_TOTAL):
        return False
    buf = []
    for ch in token[4:] + token[:4]:
        buf.append(str(ord(ch) - 55) if ch.isalpha() else ch)
    try:
        return int("".join(buf)) % 97 == 1
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def detect_financial(text: str) -> FinancialMatch | None:
    """Return the FIRST financial detail found in `text`, else None.

    Evaluation order is fixed and is part of contract K3:
    card -> routing -> account -> iban -> balance. Ordered most-specific
    first, so "routing 021000021 and account 000123456789" reports the
    routing number rather than the account.

    Pure and total: never raises, never logs, never returns the matched text.
    Returns None unconditionally when the guard is disabled.
    """
    if not text or not isinstance(text, str) or not guard_enabled():
        return None
    try:
        for m in _CARD_RE.finditer(text):
            digits = m.group(0).replace(" ", "").replace("-", "")
            if CARD_MIN_DIGITS <= len(digits) <= CARD_MAX_DIGITS and _luhn_ok(digits):
                return FinancialMatch("card", m.span())

        for m in _ROUTING_RE.finditer(text):
            digits = m.group(1) or m.group(2)
            if digits and _aba_ok(digits):
                return FinancialMatch(
                    "routing", m.span(1) if m.group(1) else m.span(2))

        m = _ACCOUNT_RE.search(text)
        if m is not None:
            return FinancialMatch("account", m.span(1))

        for m in _IBAN_RE.finditer(text):
            if _iban_ok(m.group(1)):
                return FinancialMatch("iban", m.span(1))

        for m in _MONEY_RE.finditer(text):
            try:
                amount = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if amount < BALANCE_MIN_AMOUNT:
                continue
            lo = max(0, m.start() - CONTEXT_WINDOW_CHARS)
            hi = min(len(text), m.end() + CONTEXT_WINDOW_CHARS)
            if _FIN_WORD_RE.search(text[lo:hi]):
                return FinancialMatch("balance", m.span())
    except Exception:  # noqa: BLE001 — total by contract; a detector that
        # raises inside the voice loop is worse than one that misses.
        return None
    return None
