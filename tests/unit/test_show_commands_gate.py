"""MORTIMER_VOICE_WORKFLOWS_PLAN.md D10 — show_commands last-resort gate,
with the adversarial commands it must refuse."""

from __future__ import annotations

import time

import pytest

from jarvis.bot import handoff_tools as ht


def _tool(gate):
    shown = []
    _, handler = ht.build_show_commands_tool(
        lambda payload: shown.append(payload),
        lambda: {"ok": True},
        gate=gate,
    )
    return handler, shown


@pytest.mark.parametrize("cmd", [
    "git reset --hard HEAD",
    "GIT RESET --HARD origin/main",
    "git clean -fd",
    "git clean -xdf",
    "git checkout -- .",
    "git checkout .",
    "git restore jarvis/prompts.py",
    "git push --force origin main",
    "git push --force-with-lease",
    "git push -f origin main",
    "git branch -D feat/x",
    "rm -rf build",
    "rm -f .git/index.lock",
    "rm notes.txt",
    "sudo launchctl stop x",
    "dd if=/dev/zero of=x",
    "kill -9 4242",
    "killall Python",
    "pkill -f planner",
])
def test_destructive_is_refused_even_with_needs_input(cmd):
    gate = {"needs_input_at": time.monotonic()}
    assert ht.command_gate_refusal([cmd], gate) == ht.REFUSED_DESTRUCTIVE


@pytest.mark.parametrize("cmd", [
    "git restore --staged jarvis/prompts.py",
    "git push origin feat/voice-workflows-p1",
    "git clean -n",
    "./scripts/bundle.sh",
    "git pull --rebase",
])
def test_non_destructive_human_step_is_allowed_with_needs_input(cmd):
    gate = {"needs_input_at": time.monotonic()}
    assert ht.command_gate_refusal([cmd], gate) is None


@pytest.mark.parametrize("cmd", [
    "curl -s https://openrouter.ai/api/v1/models",
    "  cat logs/bot.launchd.log",
    "ls -l macos/MortimerHost/.build",
    "git status",
    "git log --oneline -5",
    "git branch -vv",
    "open out.png",
])
def test_read_only_checks_are_refused(cmd):
    gate = {"needs_input_at": time.monotonic()}
    assert ht.command_gate_refusal([cmd], gate) == ht.REFUSED_READ_ONLY


def test_no_needs_input_is_refused():
    assert ht.command_gate_refusal(["./scripts/bundle.sh"], {}) == ht.REFUSED_NO_NEEDS_INPUT


def test_stale_needs_input_is_refused():
    gate = {"needs_input_at": 100.0}
    now = 100.0 + ht.NEEDS_INPUT_WINDOW_S + 1
    assert ht.command_gate_refusal(["./scripts/bundle.sh"], gate, now=now) == ht.REFUSED_NO_NEEDS_INPUT


def test_one_bad_command_refuses_the_whole_card():
    gate = {"needs_input_at": time.monotonic()}
    assert ht.command_gate_refusal(["./scripts/bundle.sh", "git reset --hard"], gate) == ht.REFUSED_DESTRUCTIVE


@pytest.mark.parametrize("cmd", [
    "./scripts/bundle.sh",
    "curl -s http://127.0.0.1:7861/api/status/models",   # read-only: allowed when asked
    "git status",
])
def test_explicit_ask_allows_non_destructive(cmd):
    # D-L5 (Larry, 2026-09-25): he asked for the command, no NEEDS-INPUT needed.
    assert ht.command_gate_refusal([cmd], {"explicit_ask_at": time.monotonic()}) is None


@pytest.mark.parametrize("cmd", ["git reset --hard HEAD", "rm -rf build", "sudo launchctl stop x"])
def test_destructive_is_refused_even_when_asked(cmd):
    gate = {"explicit_ask_at": time.monotonic()}
    assert ht.command_gate_refusal([cmd], gate) == ht.REFUSED_DESTRUCTIVE


def test_stale_explicit_ask_is_refused():
    now = time.monotonic()
    gate = {"explicit_ask_at": now - ht.NEEDS_INPUT_WINDOW_S - 1}
    assert ht.command_gate_refusal(["./scripts/bundle.sh"], gate, now=now) == ht.REFUSED_NO_NEEDS_INPUT


def test_no_gate_keeps_pre_plan_behaviour():
    assert ht.command_gate_refusal(["git reset --hard HEAD"], None) is None


async def test_handler_refuses_without_emitting():
    handler, shown = _tool({})
    out = await handler({"commands": ["./scripts/bundle.sh"]})
    assert out == ht.REFUSED_NO_NEEDS_INPUT and shown == []


async def test_handler_shows_allowed_command():
    handler, shown = _tool({"needs_input_at": time.monotonic()})
    out = await handler({"commands": ["./scripts/bundle.sh"]})
    assert out == "Shown in the display window." and shown[0]["commands"] == ["./scripts/bundle.sh"]


async def test_handler_without_gate_is_unchanged():
    handler, shown = _tool(None)
    out = await handler({"commands": ["curl -s https://example.com"]})
    assert out == "Shown in the display window." and len(shown) == 1


# ---------------------------------------------------------------- W8 apply
# MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 3 W8 (Larry 2026-09-25, option A):
# the one command that applies a human-only proposal Larry approved.

def test_the_apply_command_the_service_builds_is_the_one_the_gate_allows(monkeypatch):
    from jarvis.selfedit.proposals import apply_command
    for root in ("/Users/larryfix/jarvis-voice-ai-clean", "/Users/larry fix/jarvis"):
        monkeypatch.setenv("JARVIS_REPO_ROOT", root)
        command = apply_command(root, 57, "3f9c2a1b7d4e")
        assert ht.is_apply_proposal_command(command), command
        # No NEEDS-INPUT stamp and no window: the yes can come much later.
        assert ht.command_gate_refusal([command], {}) is None
        assert ht.command_gate_refusal([command], {"needs_input_at": time.monotonic() - 99_999}) is None


def test_the_apply_command_must_run_in_this_checkout(monkeypatch):
    from jarvis.selfedit.proposals import apply_command
    monkeypatch.setenv("JARVIS_REPO_ROOT", "/Users/larryfix/jarvis-voice-ai-clean")
    elsewhere = apply_command("/tmp/other-checkout", 57, "3f9c2a1b7d4e")
    assert ht.APPLY_PROPOSAL_COMMAND_RE.fullmatch(elsewhere)
    assert not ht.is_apply_proposal_command(elsewhere)
    assert ht.command_gate_refusal([elsewhere], {}) == ht.REFUSED_NO_NEEDS_INPUT


@pytest.mark.parametrize("cmd", [
    "cd /r && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e; rm -rf ~",
    "cd /r && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e && git push --force",
    "cd $(reboot) && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",
    "cd `id` && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",
    "cd /r && python scripts/apply_proposal.py 57 3f9c2a1b7d4e",
    "cd /r && .venv/bin/python scripts/apply_proposal.py 0 3f9c2a1b7d4e",
    "cd /r && .venv/bin/python scripts/other.py 57 3f9c2a1b7d4e",
    "cd r && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",                 # not absolute
    "cd =python && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",           # zsh =cmd expansion
    "cd '/r\r\x1b[2K' && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",     # hides text on screen
    "cd /r\u00e9 && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e",           # non-ASCII
    "cd /r && .venv/bin/python scripts/apply_proposal.py 57 3f9c2a1b7d4e\ngit status",    # a second line
    "cd /r && .venv/bin/python scripts/apply_proposal.py 57",                    # no digest
    "cd /r && .venv/bin/python scripts/apply_proposal.py 57 3F9C2A1B7D4E",          # not the service's form
])
def test_anything_but_the_exact_apply_command_gets_no_exemption(cmd, monkeypatch):
    monkeypatch.setenv("JARVIS_REPO_ROOT", "/r")
    assert not ht.is_apply_proposal_command(cmd)
    assert ht.command_gate_refusal([cmd], {}) is not None


def test_an_apply_command_does_not_carry_another_command_through():
    from jarvis.selfedit.proposals import apply_command
    refused = ht.command_gate_refusal([apply_command(ht.repo_root(), 5, "3f9c2a1b7d4e"), "brew install x"], {})
    assert refused == ht.REFUSED_NO_NEEDS_INPUT
