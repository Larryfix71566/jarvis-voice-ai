"""Unit tests for jarvis/clipboard.py and jarvis/bot/handoff_tools.py.

MORTIMER_HANDOFF_LOOP_PLAN.md H3/H4/H5/H6. The subprocess is stubbed —
`pbpaste` is macOS-only and these must run in CI on Linux.
"""

from __future__ import annotations

import pytest

from jarvis import clipboard as cb


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    cb.reset_for_tests()
    monkeypatch.delenv(cb.CLIPBOARD_ENABLED_ENV, raising=False)
    yield
    cb.reset_for_tests()


def _stub(monkeypatch, paste="", clear_code=0, paste_code=0):
    """Replace the subprocess layer with an in-memory pasteboard."""
    board = {"text": paste}

    def fake_run(argv, stdin=None):
        if argv[0] == "pbcopy":
            if clear_code == 0:
                board["text"] = stdin or ""
            return clear_code, ""
        return paste_code, board["text"]

    monkeypatch.setattr(cb, "_run", fake_run)
    return board


class TestArming:
    """H4/D2 — Larry's 'clear it first' made mechanical. As a habit it
    protects only when remembered; as an armed flag it protects always."""

    def test_read_without_arming_is_refused(self, monkeypatch):
        _stub(monkeypatch, paste="a password from an hour ago")
        result = cb.read()
        assert result["ok"] is False
        assert result["armed"] is False
        assert "text" not in result          # the content never leaves

    def test_clear_then_copy_then_read_works(self, monkeypatch):
        board = _stub(monkeypatch, paste="")
        assert cb.clear()["armed"] is True
        board["text"] = "ok: true, source: weather.gov"
        result = cb.read()
        assert result["ok"] is True
        assert result["text"] == "ok: true, source: weather.gov"

    def test_a_second_read_without_re_arming_is_refused(self, monkeypatch):
        board = _stub(monkeypatch)
        cb.clear()
        board["text"] = "output"
        assert cb.read()["ok"] is True
        assert cb.read()["ok"] is False       # one read per arm, always

    def test_a_failed_clear_does_not_arm(self, monkeypatch):
        """Otherwise a failed wipe would authorise reading stale content —
        the exact thing arming exists to prevent."""
        _stub(monkeypatch, paste="stale secret", clear_code=1)
        assert cb.clear()["ok"] is False
        assert cb.is_armed() is False
        assert cb.read()["ok"] is False


class TestBounds:
    def test_truncation_is_reported_never_silent(self, monkeypatch):
        board = _stub(monkeypatch)
        cb.clear()
        board["text"] = "x" * (cb.CLIPBOARD_MAX_CHARS + 500)
        result = cb.read()
        assert result["truncated"] is True
        assert len(result["text"]) == cb.CLIPBOARD_MAX_CHARS

    def test_empty_is_flagged(self, monkeypatch):
        board = _stub(monkeypatch)
        cb.clear()
        board["text"] = "   \n "
        assert cb.read()["empty"] is True

    def test_a_read_failure_is_reported(self, monkeypatch):
        _stub(monkeypatch, paste_code=127)
        cb.clear()
        assert cb.read()["ok"] is False


class TestKillSwitch:
    def test_disabled_blocks_both_verbs(self, monkeypatch):
        monkeypatch.setenv(cb.CLIPBOARD_ENABLED_ENV, "false")
        assert cb.clipboard_enabled() is False
        assert cb.clear()["ok"] is False
        assert cb.read()["ok"] is False

    def test_enabled_by_default(self):
        assert cb.clipboard_enabled() is True


class TestNoShell:
    def test_the_module_never_uses_a_shell(self):
        """Fixed argv, zero parameters — nothing to inject. This is the
        safe end of the command-execution spectrum, and deliberately not a
        precedent for a general allowlist."""
        source = open(cb.__file__, encoding="utf-8").read()
        assert "shell=True" not in source
        assert "os.system" not in source

    def test_content_is_never_logged(self):
        """The log is on disk; this text is explicitly not remembered."""
        source = open(cb.__file__, encoding="utf-8").read()
        assert "clipboard_read chars=%d" in source     # length only
        assert "text=%s" not in source


# --- handoff tools --------------------------------------------------------


class TestShowCommands:
    """H3 — a spoken command cannot be copied."""

    async def _run(self, args, arm_result=None, state=None):
        from jarvis.bot.handoff_tools import build_show_commands_tool

        sent: list[dict] = []
        armed: list[bool] = []

        def arm():
            armed.append(True)
            return arm_result if arm_result is not None else {"ok": True}

        _, handler = build_show_commands_tool(
            sent.append, arm, hint_state=state if state is not None else {})
        reply = await handler(args)
        return reply, sent, armed

    async def test_commands_go_to_the_display_window(self):
        reply, sent, _ = await self._run(
            {"title": "Check the payload", "commands": ["curl -s localhost:7861/api/ambient"]})
        assert len(sent) == 1
        assert sent[0]["surface"] == "window"
        assert sent[0]["commands"] == ["curl -s localhost:7861/api/ambient"]
        assert "curl" not in reply            # not spoken aloud

    async def test_expect_output_arms_the_clipboard(self):
        """H3.4 — arming here is what collapses four ordered steps into
        run → copy → read, and removes the copy-before-clear hazard."""
        _, sent, armed = await self._run(
            {"title": "t", "commands": ["ls"], "expect_output": True})
        assert armed == [True]
        assert sent[0]["expect_output"] is True

    async def test_no_expected_output_does_not_touch_the_clipboard(self):
        _, sent, armed = await self._run({"title": "t", "commands": ["ls"]})
        assert armed == []
        assert sent[0]["expect_output"] is False

    async def test_a_failed_arm_is_admitted_not_hidden(self):
        reply, sent, _ = await self._run(
            {"title": "t", "commands": ["ls"], "expect_output": True},
            arm_result={"ok": False, "error": "sidecar down"})
        assert "could not arm" in reply
        assert sent[0]["expect_output"] is False   # the card must not promise it

    async def test_the_return_path_is_spoken_once_per_session(self):
        """H6.2 — the card says it every time; saying it aloud every time
        is nagging."""
        state: dict = {}
        first, _, _ = await self._run(
            {"title": "t", "commands": ["ls"], "expect_output": True}, state=state)
        second, _, _ = await self._run(
            {"title": "t", "commands": ["ls"], "expect_output": True}, state=state)
        assert "read my clipboard" in first
        assert "read my clipboard" not in second

    async def test_empty_command_list_is_handled(self):
        reply, sent, _ = await self._run({"title": "t", "commands": []})
        assert sent == []
        assert "no command" in reply.lower()


class TestReadClipboardTool:
    async def _run(self, read_result):
        from jarvis.bot.handoff_tools import build_read_clipboard_tool

        injected: list[str] = []
        shown: list[dict] = []

        async def inject(text):
            injected.append(text)

        _, handler = build_read_clipboard_tool(
            lambda: read_result, inject, shown.append)
        reply = await handler({})
        return reply, injected, shown

    async def test_text_is_injected_and_shown(self):
        reply, injected, shown = await self._run(
            {"ok": True, "text": "source: weather.gov", "chars": 19,
             "truncated": False, "empty": False})
        assert injected and "source: weather.gov" in injected[0]
        assert shown and shown[0]["surface"] == "window"
        assert "19 characters" in reply

    async def test_a_refusal_is_relayed_verbatim(self):
        reply, injected, shown = await self._run(
            {"ok": False, "error": "Nothing has been copied since I last cleared."})
        assert "Nothing has been copied" in reply
        assert injected == [] and shown == []

    async def test_the_preview_lets_a_miscopy_be_caught(self):
        """H4.4 — say what it got, so the wrong thing is obvious at once."""
        reply, _, _ = await self._run(
            {"ok": True, "text": "hunter2", "chars": 7,
             "truncated": False, "empty": False})
        assert "hunter2" in reply

    async def test_empty_clipboard_says_so(self):
        reply, injected, _ = await self._run(
            {"ok": True, "text": "  ", "chars": 2, "truncated": False, "empty": True})
        assert "empty" in reply.lower()
        assert injected == []


class TestMemoryExclusion:
    """H5 — the load-bearing safety property, so it gets its own tests.

    MemoryWatcher folds the session TRANSCRIPT into long-term memory via
    an LLM extraction call. Clipboard content in the transcript could
    therefore be persisted as a durable SQLite fact — a password copied
    thirty seconds earlier included. The exclusion is structural, not a
    keyword filter, so there is nothing to tune and nothing to fail open.
    """

    def test_the_transcript_observer_only_sees_speech(self):
        """TranscriptObserver persists TranscriptionFrame — the STT
        output. Clipboard injection uses the aggregator's add_messages,
        which is not a frame at all, so it cannot be observed here."""
        import inspect

        from jarvis.bot.transcript_log import TranscriptObserver

        source = inspect.getsource(TranscriptObserver)
        assert "TranscriptionFrame" in source
        assert "clipboard" not in source.lower()

    def test_the_clipboard_path_never_creates_a_transcription_frame(self):
        """If clipboard text were pushed as a TranscriptionFrame it would
        be indistinguishable from speech and would be transcribed."""
        source = open("jarvis/bot/handoff_tools.py", encoding="utf-8").read()
        assert "TranscriptionFrame" not in source

    def test_the_injector_appends_without_pushing(self):
        """inject_silent semantics: appended to the live context so it is
        available to the model, never pushed as a turn of its own."""
        source = open("jarvis/bot/pipeline.py", encoding="utf-8").read()
        block = source.split("_inject_silent_clipboard")[1].split("def ")[0]
        assert "add_messages" in block
        assert "push_context_frame" not in block

    def test_clipboard_text_is_not_written_to_the_run_log(self):
        """Direct Supervisor tools create no agent_runs row at all — the
        clipboard tools are direct for this reason among others."""
        source = open("jarvis/bot/handoff_tools.py", encoding="utf-8").read()
        assert "RunLogger" not in source
        assert "runlog" not in source.lower()
