"""K3 detection cases (MORTIMER_SECURITY_HARDENING_PLAN.md §7.1).

Re-measured 2026-08-27 against jarvis/sensitive.py: 29 positives, 65 negatives,
0 failures, plus this repo's 68-utterance routing-eval fixture (all negative,
asserted in test_routing_eval_fixture_is_all_negative below). The negatives are
not filler — each is a shape a naive financial regex gets wrong, including the
18 that broke the first draft (owe-inside-borrowed, checking-the-build,
account-then-order-number) and this repo's own run ids, model names and tuning
constants.
"""

import pytest
import yaml

from jarvis.sensitive import (
    BALANCE_MIN_AMOUNT, FinancialMatch, detect_financial,
)
from jarvis.skills.registry import REPO_ROOT

POSITIVES = [
    # --- card (Luhn-valid test PANs) ---
    ("My Visa is 4111 1111 1111 1111", "card"),
    ("card number 4111111111111111", "card"),
    ("Amex 3782 822463 10005", "card"),
    ("put it on 5555555555554444", "card"),
    ("6011 1111 1111 1117 is the Discover", "card"),
    ("4012-8888-8888-1881", "card"),
    # --- routing (ABA-checksum-valid) ---
    ("the routing number is 021000021", "routing"),
    ("121000248 is my routing number", "routing"),
    ("ABA 011401533", "routing"),
    ("transit number 026009593", "routing"),
    # --- account (connector-chain) ---
    ("my account number is 000123456789", "account"),
    ("checking account 4829173", "account"),
    ("savings acct 88811223344", "account"),
    ("Account: 100200300400", "account"),
    # --- iban (mod-97-valid) ---
    ("IBAN GB82WEST12345698765432", "iban"),
    ("wire it to DE89370400440532013000", "iban"),
    ("FR1420041010050500013M02606", "iban"),
    # --- balance ---
    ("my balance is $2,431.09", "balance"),
    ("the checking balance dropped to $812.44", "balance"),
    ("I owe $1,250 on that one", "balance"),
    ("401k is at $118,000", "balance"),
    ("brokerage account holding $45,000", "balance"),
    ("savings has $3,000 in it", "balance"),
    ("my IRA is worth $220,400", "balance"),
    ("account balance $105.00", "balance"),
    # small real balances — review F22 (a $50 balance IS financial) ---
    ("my checking account balance is $47.32", "balance"),
    ("my savings balance is $50", "balance"),
    ("the account balance is $88.10", "balance"),
    # assistant-shaped reply — review F2 (the reply is now scanned) ---
    ("Your checking account balance is $2,431.18 as of today.", "balance"),
]

NEGATIVES = [
    # phone numbers — 4 shapes
    "call me at 555-123-4567",
    "(205) 555-0134",
    "1-800-555-0199",
    "my phone is 205 555 0134",
    # zip codes
    "my zip is 35242",
    "ship it to zip 35242-1234",
    # dates and timestamps
    "the meeting is on 2026-08-27",
    "2026-08-27T14:32:00Z",
    # order / confirmation numbers
    "order number 10023344",
    "confirmation 8837-2210",
    "the PR is #1423 and the issue is #98",
    # this repo's own run ids and commits
    "run id 462da350",
    "run 97d5cecc failed",
    "analyst runs 462da350, 97d5cecc, 9bd877dc all failed",
    "the commit is 9ed79982e1",
    # model and version strings
    "the model is gpt-5.1",
    "we're on version 2.1.4",
    "pipecat 1.4.0",
    "elevenlabs eleven_flash_v2_5",
    # small money without a financial noun, and with a verb-y one
    "grab lunch, $20 for lunch on Friday",
    "it cost $8.50",
    "my account was charged $8.50",       # $8.50 < floor; account not a number
    "he owes me $20 for lunch",           # "owes" != owe/owed (boundary)
    # financial nouns with no value
    "my account is locked again",
    "check the savings on that deal",
    "route 280 is backed up",
    "the routing eval scored 92%",
    # the case-sensitivity trap for IRA
    "Ira paid me $500 back",
    # bare numbers in ordinary speech
    "remind me in 15 minutes",
    "set a timer for 90 seconds",
    "temperature is 91 degrees",
    "I have 1234 unread emails",
    # this repo's own constants and identifiers
    "MAX_PAYLOAD_BYTES = 5000000",
    "set max_iterations to 25 and timeout_s to 300",
    # checksum traps: right shape, wrong check digit
    "1234 5678 9012 3456",
    "GB82WEST12345698765433",
    # review F3 — "owe" as a substring, near an amount >= floor (was 11 FPs)
    "the invoice showed $1,299 for the laptop",
    "I lowered the offer to $250",
    "he borrowed $400 from his brother",
    "however, $250 is too much for a mouse",
    "the crowd allowed $150 tickets",
    "sales slowed after the $300 hike",
    "the flowers cost $120",
    "she followed up on the $900 invoice",
    "the tower repair was $2,000",
    "vowel training software is $150",
    # review F3 — repo prose substrings near money
    "the lowest price was $500",
    "she narrowed it to $300 options",
    "powers of ten like $1000",
    "the shadowed panel cost $200 to fix",
    "I swallowed the $150 fee",
    "windowed mode dropped to $99",
    "accounting for $5000 in scope",
    "lowering the bar to $250",
    # review F3 — bare-verb "checking"/"savings" + a long id (was 8 FPs)
    "checking the run at 1756254000 now",
    "I'm checking build 1049322 for errors",
    "checking on that, the PR is 1234567",
    "checking flight 1234567 status",
    "my account, the order number is 8675309",
    "my Amazon account, order 112233445 shipped",
    "log in to my account, my member id is 998877",
    "savings of 1500000 tokens per run",
    # review F22 — trivial IOUs with the verb "owe" (floor rejects sub-$25)
    "I owe you $20 for lunch",
    "you owe me $15",
    "owe Dave $20 for lunch",
]


@pytest.mark.parametrize("text,kind", POSITIVES)
def test_positive(text, kind):
    match = detect_financial(text)
    assert match is not None, f"missed: {text!r}"
    assert match.kind == kind, f"{text!r} -> {match.kind}, want {kind}"


@pytest.mark.parametrize("text", NEGATIVES)
def test_negative(text):
    assert detect_financial(text) is None, f"false positive: {text!r}"


def test_counts_match_the_plan():
    """Guards against a case being quietly deleted to make the suite pass."""
    assert len(POSITIVES) == 29
    assert len(NEGATIVES) == 65


def test_routing_eval_fixture_is_all_negative():
    """C7 / review corpus: every routing-eval utterance is a non-financial
    turn and must never arm the detector (0 false alarms on the real fixture)."""
    cases = yaml.safe_load((REPO_ROOT / "tests" / "evals" / "cases.yaml").read_text())
    fired = [c["input"] for c in cases if detect_financial(c["input"]) is not None]
    assert not fired, f"detector fired on routing-eval utterances: {fired}"


def test_span_covers_only_the_token():
    """span is the sensitive token, never the keyword context (D-H3)."""
    text = "the routing number is 021000021"
    match = detect_financial(text)
    assert text[match.span[0]:match.span[1]] == "021000021"

    text = "my balance is $2,431.09"
    match = detect_financial(text)
    assert text[match.span[0]:match.span[1]] == "$2,431.09"


def test_order_is_most_specific_first():
    """A string with both a routing number and an account number reports
    the routing number (D-H3 fixed order)."""
    match = detect_financial("routing 021000021 and account 000123456789")
    assert match.kind == "routing"


def test_total_never_raises():
    for value in (None, "", "a" * 20000, "\x00\x01\x02", "​", 12345, []):
        assert detect_financial(value) is None


def test_kill_switch(monkeypatch):
    card = "My Visa is 4111 1111 1111 1111"
    assert detect_financial(card) is not None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "false")
    assert detect_financial(card) is None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "0")
    assert detect_financial(card) is None
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "true")
    assert detect_financial(card) is not None


def test_balance_floor_is_the_knob(monkeypatch):
    """R-5/F22: the floor is what separates a trivial IOU from a balance.
    "owe" matches the keyword (boundary-safe), so only the $20 < 25 floor
    keeps this negative; at floor 0 the roadmap's literal rule returns it."""
    assert detect_financial("I owe you $20 for lunch") is None
    monkeypatch.setattr("jarvis.sensitive.BALANCE_MIN_AMOUNT", 0.0)
    assert detect_financial("I owe you $20 for lunch") is not None


def test_word_boundary_keeps_owe_out_of_borrowed():
    """review F3: the boundary fix, not the floor, is what rejects these."""
    for text in ("he borrowed $400 from his brother",
                 "the invoice showed $1,299 for the laptop",
                 "I lowered the offer to $250"):
        assert detect_financial(text) is None, text


def test_account_connector_chain_rejects_competing_nouns():
    """review F3: a competing noun between 'account' and the digits breaks
    the chain, so an order/member number near 'account' is not an account."""
    assert detect_financial("my account, the order number is 8675309") is None
    assert detect_financial("checking build 1049322 for errors") is None
    assert detect_financial("my account number is 000123456789").kind == "account"


def test_returns_a_frozen_dataclass():
    match = detect_financial("card number 4111111111111111")
    assert isinstance(match, FinancialMatch)
    with pytest.raises(Exception):
        match.kind = "balance"
