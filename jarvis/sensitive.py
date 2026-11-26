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


# --------------------------------------------------------------------------
# Credentials (Larry, 2026-11-24: account or password info must not leave the
# Mac). Literal key/token shapes, and a typed password/secret assignment. A
# password spoken in a sentence ("the password is wrong") is deliberately
# not matched: it cannot be told apart from talk about passwords.
# --------------------------------------------------------------------------

_CREDENTIAL_RES = (
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:password|passwd|passcode|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*\S{4,}"),
)


def detect_credential(text: str) -> bool:
    """True when `text` holds a credential literal. Never returns the match."""
    if not guard_enabled() or not isinstance(text, str) or not text:
        return False
    return any(pattern.search(text) for pattern in _CREDENTIAL_RES)


# --------------------------------------------------------------------------
# Spoken credentials (design: spoken-password-guard, option A). A password,
# PIN or code SPOKEN in a sentence ("my password is hunter2") cannot be told
# apart from talk about passwords by `detect_credential` above, so this is a
# separate, flag-gated detector. It returns SPANS of the VALUE only (never the
# matched text); redaction replaces just those spans. OFF by default: with the
# flag unset nothing here finds, redacts or arms anything.
# --------------------------------------------------------------------------

SPOKEN_CREDENTIAL_GUARD_ENV = "JARVIS_SPOKEN_CREDENTIAL_GUARD_ENABLED"
SPOKEN_CREDENTIAL_WORD_VALUES_ENV = "JARVIS_SPOKEN_CREDENTIAL_WORD_VALUES"
SPOKEN_CREDENTIAL_BARE_CODE_ENV = "JARVIS_SPOKEN_CREDENTIAL_BARE_CODE"
SPOKEN_CREDENTIAL_PLACEHOLDER = "[secret kept on this Mac]"

_FALSE_VALUES = ("0", "false", "no", "off")


def spoken_guard_enabled() -> bool:
    """True only on an explicit truthy flag AND the master guard being on."""
    raw = os.environ.get(SPOKEN_CREDENTIAL_GUARD_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on") and guard_enabled()


def _word_values_enabled() -> bool:
    return os.environ.get(SPOKEN_CREDENTIAL_WORD_VALUES_ENV, "").strip().lower() not in _FALSE_VALUES


def _bare_code_enabled() -> bool:
    return os.environ.get(SPOKEN_CREDENTIAL_BARE_CODE_ENV, "").strip().lower() not in _FALSE_VALUES


_WORD_N = r"(?:passwords?|passwd|passcode|passphrase|pass[ ]phrase)"
_QUAL_CODE = (r"(?:security|access|door|gate|alarm|garage|lock|unlock|entry|"
              r"verification|keypad|safe|lockbox)\s+code")
_DIGIT_N = rf"(?:pin(?:\s+(?:number|code))?|{_QUAL_CODE})"
_DET = r"(?:the|my|our|your|his|her|their)"
_BARE_N = rf"{_DET}\s+code"

_QUAL = r"(?:\s+(?:for|to|on|of|at)(?:\s+[\w'’-]+){1,4}?)?"
_LINK = (r"(?:['’]s(?:\s+now)?|\s+(?:is\s+now|is|was|are|should\s+be|will\s+be)\b"
         r"|\s*[:=])")
_VERBS = r"(?:set|change|changed|update|updated|reset)"

_MAIN_RES = {
    "word": re.compile(rf"(?i)\b{_WORD_N}\b{_QUAL}{_LINK}"),
    "digit": re.compile(rf"(?i)\b{_DIGIT_N}\b{_QUAL}{_LINK}"),
    "bare": re.compile(rf"(?i)\b{_BARE_N}\b{_QUAL}{_LINK}"),
}
_VERB_RES = {
    "word": re.compile(rf"(?i)\b{_VERBS}\s+(?:(?:the|my|your|our)\s+)?(?:[\w-]+\s+){{0,2}}?"
                       rf"{_WORD_N}\b\s+to\s+"),
    "digit": re.compile(rf"(?i)\b{_VERBS}\s+(?:(?:the|my|your|our)\s+)?(?:[\w-]+\s+){{0,2}}?"
                        rf"{_DIGIT_N}\b\s+to\s+"),
    "bare": re.compile(rf"(?i)\b{_VERBS}\s+{_BARE_N}\b\s+to\s+"),
}

_WORD_RE = re.compile(r"[\w'’-]+")
_FILLER_RE = re.compile(r"(?i)(?:now|actually)\b\s*")

_STOP_WORDS = frozenset("""
on in at under below above behind inside near by written taped stuck saved stored printed
listed posted kept somewhere here there a an the my your his her their our its it this that
what how why where when which who required needed missing blank empty case case-sensitive
too very really pretty kind sort supposed going being getting changing working broken for
about of and or just also already still never always usually probably like something same
different changed set reset locked expiring encrypted hashed long short longer shorter weak
strong easy hard simple complicated secure insecure fine ok okay good bad great terrible
unknown forgotten lost gone incorrect invalid expired mandatory optional protected hidden
visible shown no it's that's isn't doesn't don't can't won't
""".split())
_COND_WORDS = frozenset(("wrong", "right", "correct"))
_COND_TAIL_RE = re.compile(
    r"(?i)(?:\s+(?:again|now|anymore|though|too|then|today|apparently|right))?\s*$")

_CLAUSE_END_RE = re.compile(
    r"(?i)[.,;!?…](?=\s|$)"
    r"|\s+(?:and|but|so|then)\s+(?:can|could|would|will|please|i|i['’]m|i['’]ll|you|we|he|"
    r"she|they|it|that|what|how|text|send|tell|save|remember|use|type|enter|log|sign|put|also|"
    r"then|don['’]t|do)\b"
    r"|\s+(?:please|thanks)\b|\s+thank\s+you\b|\s+(?:can|could|would|will)\s+you\b")

_NUM_WORDS = (r"zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
              r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
              r"sixty|seventy|eighty|ninety|hundred|double|triple")
_TOK = rf"(?:\d+|{_NUM_WORDS})(?![\w'’])"
_RUN_RE = re.compile(rf"(?i){_TOK}(?:[\s,-]+(?:{_TOK}|o(?![\w'’])))*")
_UNIT_RE = re.compile(
    r"(?i)\s*(?:%|o['’]clock\b|(?:lines?|characters?|chars|bytes|kb|mb|gb|files?|percent|"
    r"seconds?|secs?|minutes?|mins?|hours?|days?|weeks?|months?|years?|times|errors?|tests?|"
    r"words?|pages?|steps?|items?|ms|pm|am|dollars?|bucks|degrees|digits?|letters?|long)\b)")

_NATO = frozenset("""alpha bravo charlie delta echo foxtrot golf hotel india juliett juliet kilo
lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey whisky xray x-ray
yankee zulu""".split())

_REFUSAL_RE = re.compile(
    r"(?i)^\W*(?:never\s*mind|no|nope|cancel|stop|forget\s+it|i\s+don['’]?t\s+know|"
    r"i\s+forgot|i\s+forget|why|what|skip|not\s+now|later|hold\s+on|wait)\b")
_LEADIN_RE = re.compile(
    r"(?i)^\W*(?:(?:it['’]?s|it\s+is|that['’]?s|that\s+is|sure|okay|ok|yes|yeah|yep|um|uh)\b[\s,:-]*)+")
_FILLER_ONLY_RE = re.compile(r"(?i)^[\W]*(?:(?:um+|uh+)\b[\W]*)*$")


def _clause_end(text: str, start: int) -> int:
    m = _CLAUSE_END_RE.search(text, start)
    end = m.start() if m else len(text)
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _digit_value(text: str, i: int) -> tuple[int, int] | None:
    m = _RUN_RE.match(text, i)
    if m is None:
        return None
    if _UNIT_RE.match(text, m.end()):
        return None
    return (i, m.end())


def _strict_ok(value: str) -> bool:
    """WORD_VALUES off: a word noun's value must look like a secret."""
    if _RUN_RE.match(value):
        return True
    words = value.split()
    if not words:
        return False
    if any(c.isdigit() for c in words[0]):
        return True
    if len(words) >= 2:
        def spelled(w: str) -> bool:
            w = w.strip(".,").lower()
            return (len(w) == 1 and w.isalpha()) or w in _NATO
        return spelled(words[0]) and spelled(words[1])
    return False


def _stops(text: str, wm: "re.Match[str]", start: int) -> bool:
    """True when the word at `wm` means the value is talk, not a password."""
    w = wm.group(0).lower()
    if w in _STOP_WORDS:
        return True
    if w in _COND_WORDS:
        end = _clause_end(text, start)
        return bool(_COND_TAIL_RE.match(text, wm.end(), end) or
                    _COND_TAIL_RE.fullmatch(text[wm.end():end]))
    return False


def _value_after(text: str, pos: int, kind: str) -> tuple[int, int] | None:
    n = len(text)
    i = pos
    while i < n and text[i].isspace():
        i += 1
    fm = _FILLER_RE.match(text, i)
    if fm and fm.end() < n:
        i = fm.end()
    while i < n and text[i] in "\"'“”‘’`":
        i += 1
    if i >= n or text[i] == "[" or text[i] in ".,;!?…":
        return None
    if kind in ("digit", "bare"):
        return _digit_value(text, i)
    start = i
    # "passwords are 8 characters": a length, not a password.
    run = _RUN_RE.match(text, i)
    if run is not None and _UNIT_RE.match(text, run.end()):
        return None
    wm = _WORD_RE.match(text, i)
    if wm is not None:
        w = wm.group(0).lower()
        j = wm.end()
        negated = False
        if w == "not":
            negated = True
        elif w == "no":
            lm = re.compile(r"(?i)\s+longer\b").match(text, j)
            if lm:
                negated, j = True, lm.end()
        if negated:
            k = j
            while k < n and text[k].isspace():
                k += 1
            wm2 = _WORD_RE.match(text, k)
            if wm2 is None or _stops(text, wm2, k):
                return None
            start = k
        elif _stops(text, wm, i):
            return None
    end = _clause_end(text, start)
    if end <= start:
        return None
    if not _word_values_enabled() and not _strict_ok(text[start:end]):
        return None
    return (start, end)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _pending_span(text: str) -> tuple[int, int] | None:
    stripped = text.strip()
    if (not stripped or len(stripped.split()) > 8
            or SPOKEN_CREDENTIAL_PLACEHOLDER in text):
        return None
    if _FILLER_ONLY_RE.match(stripped) or _REFUSAL_RE.match(stripped):
        return None
    lead = _LEADIN_RE.match(text)
    i = lead.end() if lead else 0
    while i < len(text) and not text[i].isalnum() and text[i] not in "$#@!%&*":
        if text[i] == "[":
            return None
        i += 1
    if i >= len(text) or text[i] == "[":
        return None
    end = _clause_end(text, i)
    return (i, end) if end > i else None


def find_spoken_credential_spans(text: str, *, pending: bool = False) -> list[tuple[int, int]]:
    """Sorted, merged spans of spoken credential VALUES. Total; [] when off."""
    if not text or not isinstance(text, str) or not spoken_guard_enabled():
        return []
    try:
        spans: list[tuple[int, int]] = []
        kinds = ["word", "digit"] + (["bare"] if _bare_code_enabled() else [])
        for kind in kinds:
            for rx in (_MAIN_RES[kind], _VERB_RES[kind]):
                pos = 0
                while pos <= len(text):
                    m = rx.search(text, pos)
                    if m is None:
                        break
                    span = _value_after(text, m.end(), kind)
                    if span is not None:
                        spans.append(span)
                        pos = max(m.end(), span[1])
                    else:
                        pos = m.end()
        if pending and not spans:
            span = _pending_span(text)
            if span is not None:
                spans.append(span)
        return _merge(spans)
    except Exception:  # noqa: BLE001 — total by contract
        return []


def redact_spoken_credentials(text: str, *, pending: bool = False) -> str:
    """`text` with each credential value replaced by the placeholder."""
    spans = find_spoken_credential_spans(text, pending=pending)
    if not spans:
        return text
    out, last = [], 0
    for s, e in spans:
        out.append(text[last:s])
        out.append(SPOKEN_CREDENTIAL_PLACEHOLDER)
        last = e
    out.append(text[last:])
    return "".join(out)


def detect_spoken_credential(text: str, *, pending: bool = False) -> bool:
    return bool(find_spoken_credential_spans(text, pending=pending))


_TRAIL = r"[\s.…!?:,\"'“”‘’-]*$"
_PENDING_RES = None


def _pending_res():
    global _PENDING_RES
    if _PENDING_RES is None:
        any_n = f"(?:{_WORD_N}|{_DIGIT_N}|{_BARE_N})"
        any_n_verb = f"(?:{_WORD_N}|{_DIGIT_N})"
        _PENDING_RES = (
            re.compile(rf"(?i)\b{any_n}\b{_QUAL}{_LINK}(?:\s+(?:now|actually))?{_TRAIL}"),
            re.compile(rf"(?i)\b{_VERBS}\s+(?:(?:the|my|your|our)\s+)?(?:[\w-]+\s+){{0,2}}?"
                       rf"{any_n_verb}\b\s+to{_TRAIL}"),
            re.compile(rf"(?i)\bhere(?:['’]s|\s+is)\s+(?:(?:my|the|our)\s+)?"
                       rf"(?:[\w-]+\s+){{0,2}}?(?:{_WORD_N}|{_DIGIT_N}|{_BARE_N}){_TRAIL}"),
        )
    return _PENDING_RES


_DOUBT_WORDS = frozenset(("what", "which", "where", "how", "whether", "if", "know", "forgot",
                          "remember", "tell"))


def leaves_credential_pending(text: str) -> bool:
    """True when the utterance ends right where a credential value should start."""
    if not text or not isinstance(text, str) or not spoken_guard_enabled():
        return False
    try:
        for rx in _pending_res():
            m = rx.search(text)
            if m is None:
                continue
            prefix = [w.strip("'’,.?!").lower() for w in text[:m.start()].split()[-3:]]
            if any(w in _DOUBT_WORDS or w.split("'")[0] in _DOUBT_WORDS for w in prefix):
                continue
            if not _bare_code_enabled() and _BARE_ONLY_RE.search(m.group(0)):
                continue
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


_BARE_ONLY_RE = re.compile(rf"(?i)^\W*{_DET}\s+code\b")

_ASK_PHRASE = (r"(?:what(?:['’]s|\s+is)|tell\s+me|give\s+me|read\s+me|say|send\s+me|"
               r"i\s+need|i['’]ll\s+need|enter|type|share)")
_ASK_RE = re.compile(
    rf"(?i)\b{_ASK_PHRASE}\s+(?:(?:(?:the|your|my|a|an)\s+)?(?:[\w'’-]+\s+){{0,2}}?"
    rf"(?:{_WORD_N}|{_DIGIT_N})\b|(?:the|your|my)\s+code\b)"
    r"(?!\s+(?:manager|reset|policy|rules?|requirements?|length|field|box))")


def asks_for_credential(text: str) -> bool:
    """True when an assistant reply asks the user to say or type a credential."""
    if not text or not isinstance(text, str) or not spoken_guard_enabled():
        return False
    try:
        m = _ASK_RE.search(text)
        if m is None:
            return False
        if not _bare_code_enabled() and _BARE_TAIL_RE.search(m.group(0)):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


_BARE_TAIL_RE = re.compile(r"(?i)\b(?:the|your|my)\s+code\b$")
