"""Sidecar-side reminder notifier (gap-closure plan GC9). The bot's
RemindersWatcher lives inside a WebRTC session; this thread lives as long
as the sidecar, and only ever sets reminders.notified_at — never delivered."""
from __future__ import annotations
import logging, threading
from typing import Callable
from mcp_servers.mcp_reminders import logic
from jarvis.notify import post_notification
logger = logging.getLogger(__name__)
REMINDER_NOTIFY_INTERVAL_S = 30.0   # §6
REMINDER_NOTIFY_GRACE_S = 60.0      # §6

class ReminderNotifier:
    def __init__(self, interval_s: float = REMINDER_NOTIFY_INTERVAL_S,
                 grace_s: float = REMINDER_NOTIFY_GRACE_S,
                 post: Callable[[str], bool] = post_notification):
        self._interval_s, self._grace_s, self._post = interval_s, grace_s, post
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="reminder-notifier", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            self.tick_once()

    def tick_once(self) -> int:
        """Notify every due-but-unspoken reminder once. Returns the count. Never raises."""
        try:
            rows = logic.peek_due_reminders(self._grace_s).get("reminders") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("reminder_notifier_peek_failed error=%s", type(exc).__name__)
            return 0
        sent = 0
        for row in rows:
            if self._post(str(row.get("message", ""))):
                try:
                    logic.mark_notified([int(row["id"])])
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reminder_notifier_mark_failed id=%s error=%s", row.get("id"), type(exc).__name__)
        return sent
