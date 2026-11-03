"""Mail brief assembly (WS-13 P3m, plan R.0f / R.10.3 / R.10.10 / R.10.16).

Pure and deterministic: no I/O, no logging, no clock reads (the caller passes
``now`` and ``tz``). It turns the dict that ``mcp_mail.logic.mail_headlines``
returns into a typed ``brief`` section and into the display payload the
native app renders as literal text.

Two rules shape everything here:

* Source text (sender, subject) lives only inside ``payload["brief"]``. The
  generic ``title`` and ``body`` are fixed host strings, so an older app, a
  log line or a speech path can never carry mail content.
* A count that is not exact is never shown as a number alone: a lower bound
  reads "at least N" and an unknown count reads "unknown", never zero.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

BRIEF_VERSION = 1
MAX_HEADLINES = 10
MAX_FIELD_CHARS = 200

#: Fixed host text for the generic body (never source text).
BODY_TEXT = ("Your mail headlines are in this card. "
             "Update the Mortimer app if you can't see them.")
TITLE = "Mail"
HEADER_UNAVAILABLE = "(header unavailable)"

#: R.10.3 source-status codes this increment can produce.
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_DISABLED = "disabled"
_KNOWN_STATUSES = frozenset({STATUS_OK, STATUS_PARTIAL, STATUS_FAILED, STATUS_TIMEOUT,
                             STATUS_NOT_CONFIGURED, STATUS_DISABLED})

STATUS_TEXT = {
    STATUS_OK: "Signed in",
    STATUS_PARTIAL: "Partly read",
    STATUS_FAILED: "Couldn't read",
    STATUS_TIMEOUT: "Timed out",
    STATUS_NOT_CONFIGURED: "Not set up",
    STATUS_DISABLED: "Mail is turned off",
}

REASON_LOGIN = "login rejected"
REASON_CONNECT = "couldn't connect"
REASON_READ = "couldn't read"

#: Closed allowlist: server abort reason -> fixed host label. Anything not
#: listed becomes REASON_READ; raw server text never reaches the card.
_REASON_LABELS = {
    "login_rejected": REASON_LOGIN,
    "tls": REASON_CONNECT,
    "network": REASON_CONNECT,
    "server_abort": REASON_CONNECT,
    "connection_closed": REASON_CONNECT,
    "worker_start": REASON_CONNECT,
}

#: Display labels are host-owned, keyed by account key. The server's own
#: label for "att" is the mail domain, not what Larry calls the account.
_ACCOUNT_LABELS = {"gmail": "Gmail", "att": "AT&T"}
_ACCOUNT_ORDER = ("gmail", "att")

COUNT_UNKNOWN = "unknown"


def _clean(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    """Literal text only: control characters (and line breaks) removed,
    bounded length. No Markdown handling of any kind."""
    if not isinstance(value, str):
        return ""
    text = "".join(" " if ch in "\r\n\t" else ch for ch in value
                   if ch in "\r\n\t" or (ord(ch) >= 32 and ord(ch) != 127
                                         and not 0x80 <= ord(ch) <= 0x9F
                                         and ch not in "  ‎‏"
                                         and not 0x202A <= ord(ch) <= 0x202E
                                         and not 0x2066 <= ord(ch) <= 0x2069))
    return " ".join(text.split())[:limit]


def _count(count: Any, status: str) -> tuple[str, int | None, str]:
    """(state, value, text). Unknown never becomes zero (R.10.10)."""
    if isinstance(count, dict):
        state, value = count.get("state"), count.get("value")
        if (state in ("exact", "lower_bound") and isinstance(value, int)
                and not isinstance(value, bool) and value >= 0):
            if state == "exact":
                return "exact", value, str(value)
            return "lower_bound", value, f"at least {value}"
    return "unknown", None, COUNT_UNKNOWN


def _account(raw: dict) -> dict:
    key = _clean(raw.get("key"), 32)
    status = raw.get("status")
    if status not in _KNOWN_STATUSES:
        status = STATUS_FAILED
    label = _ACCOUNT_LABELS.get(key) or _clean(raw.get("label"), 40) or key or "Mail"
    reason = None
    if status == STATUS_FAILED:
        reason = _REASON_LABELS.get(raw.get("error") if isinstance(raw.get("error"), str) else "",
                                    REASON_READ)
    state, value, text = _count(raw.get("count"), status)
    return {
        "key": key, "label": label, "status": status,
        "status_text": STATUS_TEXT[status], "reason": reason,
        "count_state": state, "count_value": value, "count_text": text,
    }


def _failed_account(key: str, *, status: str = STATUS_FAILED) -> dict:
    return {
        "key": key, "label": _ACCOUNT_LABELS[key], "status": status,
        "status_text": STATUS_TEXT[status],
        "reason": REASON_READ if status == STATUS_FAILED else None,
        "count_state": "unknown", "count_value": None, "count_text": COUNT_UNKNOWN,
    }


def _received_local(value: Any, now: datetime, tz: tzinfo) -> str:
    if not isinstance(value, str):
        return ""
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            return ""
        local = moment.astimezone(tz)
        today = now.astimezone(tz).date()
    except (ValueError, OverflowError):
        return ""
    clock = local.strftime("%H:%M")
    return clock if local.date() == today else f"{local.strftime('%a')} {clock}"


def _headline(raw: dict, labels: dict[str, str], now: datetime, tz: tzinfo) -> dict:
    unavailable = bool(raw.get("fields_unavailable"))
    sender = HEADER_UNAVAILABLE if unavailable else _clean(raw.get("sender"))
    subject = HEADER_UNAVAILABLE if unavailable else _clean(raw.get("subject"))
    account = raw.get("account")
    return {
        "account_label": labels.get(account, _clean(account, 40)) if isinstance(account, str) else "",
        "sender": sender,
        "subject": subject,
        "received_local": _received_local(raw.get("received_at"), now, tz),
    }


def assemble_mail_brief(envelope_content: dict | None, *, error: str | None,
                        now: datetime, tz: tzinfo) -> dict:
    """The typed mail section. ``error`` (a closed, content-free code from the
    caller) or any unusable content yields every account ``failed``; the
    result is still a valid card. The returned dict is the section
    (``source``, ``accounts``, ``headlines``, ``more``) plus two bookkeeping
    keys that ``build_brief_payload`` lifts out of it: ``outcome``
    (``full`` | ``partial`` | ``all_failed``) and ``generated_at_local``."""
    content = envelope_content
    accounts: list[dict]
    headlines: list[dict] = []
    more = 0
    if error is None and isinstance(content, dict) and content.get("ok") is False \
            and content.get("error") == "mail_disabled":
        accounts = [_failed_account(key, status=STATUS_DISABLED) for key in _ACCOUNT_ORDER]
    elif (error is None and isinstance(content, dict) and content.get("ok") is True
          and isinstance(content.get("accounts"), list)
          and all(isinstance(a, dict) for a in content["accounts"])
          and content["accounts"]):
        accounts = [_account(a) for a in content["accounts"]]
        labels = {a["key"]: a["label"] for a in accounts}
        messages = content.get("messages")
        usable = [m for m in messages if isinstance(m, dict)] if isinstance(messages, list) else []
        # Newest first by the server's own receipt instant (ISO strings with an
        # offset sort by instant only after parsing; unparseable sort last).
        def instant(m: dict) -> float:
            try:
                return datetime.fromisoformat(str(m.get("received_at"))).timestamp()
            except (ValueError, OverflowError):
                return float("-inf")
        usable.sort(key=instant, reverse=True)
        headlines = [_headline(m, labels, now, tz) for m in usable[:MAX_HEADLINES]]
        more = max(0, len(usable) - MAX_HEADLINES)
    else:
        accounts = [_failed_account(key) for key in _ACCOUNT_ORDER]
    statuses = [a["status"] for a in accounts]
    if all(s == STATUS_OK for s in statuses):
        outcome = "full"
    elif not any(s in (STATUS_OK, STATUS_PARTIAL) for s in statuses):
        outcome = "all_failed"
    else:
        outcome = "partial"
    return {"source": "mail", "accounts": accounts, "headlines": headlines, "more": more,
            "outcome": outcome,
            "generated_at_local": now.astimezone(tz).strftime("%Y-%m-%d %H:%M")}


def build_brief_payload(section: dict, *, result_id: str, ts: float) -> dict:
    """The display payload for a ``brief`` card from an assembled section.
    ``title`` and ``body`` are fixed host strings: no source text ever
    reaches them."""
    body_section = {k: v for k, v in section.items()
                    if k not in ("outcome", "generated_at_local")}
    return {
        "kind": "brief",
        "title": TITLE,
        "body": BODY_TEXT,
        "brief": {"version": BRIEF_VERSION, "sections": [body_section],
                  "generated_at_local": section.get("generated_at_local", "")},
        "images": [],
        "basemap_images": [],
        "links": [],
        "agent": "Mortimer",
        "run_id": "",
        "ts": ts,
        "surface": "window",
        "tool": "daily_brief",
        "data_policy": "confidential",
        "arrival": "requested",
        "result_id": result_id,
        "revision": 1,
        "outcome": section["outcome"],
    }
