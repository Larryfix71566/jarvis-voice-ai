"""Keep the two active implementation plans honest about landed artifacts.

The plans are the architectural contract. This test is intentionally a small
file-presence gate: it catches a plan claiming implementation while a required
source, fixture, test, or acceptance document has disappeared. The one
documented filename alias reflects the landed Command Console suite's name.
"""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]


COMMAND_CONSOLE_ARTIFACTS = (
    "macos/MortimerHost/Sources/MortimerHost/App/ConsoleActionCoordinator.swift",
    "macos/MortimerHost/Sources/MortimerHost/App/ConsoleActionRegistry.swift",
    "macos/MortimerHost/Sources/MortimerHost/Stores/AtlasStore.swift",
    "macos/MortimerHost/Sources/MortimerHost/Stores/PanelStore.swift",
    "macos/MortimerHost/Sources/MortimerHost/Stores/AttachmentStore.swift",
    "macos/MortimerHost/Sources/MortimerHost/Stores/SharedMediaStore.swift",
    "macos/MortimerHost/Sources/MortimerHost/Console/CommandConsoleView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Console/VoiceConsoleView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Display/KnowledgeAtlasView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Display/AtlasCardView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Display/ContentPanelView.swift",
    "macos/MortimerHost/Sources/MortimerHost/App/AppMessageRouter.swift",
    "macos/MortimerHost/Sources/MortimerHost/App/ResponseResultRouter.swift",
    "macos/MortimerHost/Sources/MortimerHost/Display/ShareCoordinator.swift",
    "macos/MortimerHost/Sources/MortimerHost/Display/SharePreviewView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Console/AttachmentTrayView.swift",
    "macos/MortimerHost/Sources/MortimerHost/Console/AttachmentNormalizer.swift",
    "macos/MortimerHost/Sources/MortimerHost/Placement/ContentWindowRegistry.swift",
    "macos/JarvisKit/Sources/JarvisKit/ConsoleProtocol.swift",
    "macos/JarvisKit/Sources/JarvisKit/SharedContentTransfer.swift",
    "macos/JarvisKit/Sources/JarvisKit/MessagePrivacy.swift",
    "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift",
    "macos/MortimerHost/Sources/MortimerHost/Drawer/RepoTab.swift",
    "jarvis/repo_map.py",
    "docs/ARCHITECTURE.md",
    "jarvis/bot/console_protocol.py",
    "jarvis/bot/console_session.py",
    "jarvis/bot/console_actions.py",
    "jarvis/bot/shared_content.py",
    "jarvis/bot/shared_content_transfer.py",
    "jarvis/vision.py",
    "tests/unit/test_console_protocol.py",
    "tests/unit/test_console_session.py",
    "tests/unit/test_console_actions.py",
    "tests/unit/test_shared_content.py",
    "tests/unit/test_vision_profile.py",
    "tests/unit/test_architecture_reference.py",
    "macos/MortimerHost/Tests/MortimerHostTests/ScreenPlacementTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/FullConsoleRenderingTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/VoiceWaveRenderingTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/KnowledgeAtlasTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/ContentPanelTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/SupportingDisplayAcceptanceTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/ResponseResultRouterTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/DisplayPlacementPolicyTests.swift",
    "macos/MortimerHost/Tests/MortimerHostTests/DisplayPanelSizingTests.swift",
    "docs/acceptance/command-console/probes/DisplayTopologyProbe.swift",
    "scripts/run_display_topology_probe.sh",
    "tests/fixtures/command_console/protocol.json",
    "tests/fixtures/command_console/voice_cases.json",
    "docs/acceptance/command-console/STATUS.md",
    "docs/acceptance/command-console/PRESERVATION.md",
    "docs/acceptance/command-console/VOICE.md",
    "docs/acceptance/command-console/SHARING.md",
    "docs/acceptance/command-console/DISPLAYS.md",
    "docs/acceptance/command-console/PERFORMANCE.md",
    "docs/acceptance/command-console/RELEASE.md",
    "docs/acceptance/command-console/receipts/display-topology-2026-09-18.json",
    "docs/acceptance/command-console/receipts/display-topology-2026-09-18-two-screen.json",
    "docs/acceptance/command-console/receipts/display-topology-2026-09-18-current.json",
    "docs/acceptance/command-console/receipts/display-content-policy-2026-09-18.md",
    "docs/acceptance/command-console/receipts/live-app-connection-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-two-screen-roles-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-two-screen-content-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-external-stage-current-2026-09-18.md",
    "docs/acceptance/command-console/receipts/sandbox-verification-2026-09-18.md",
    "docs/acceptance/command-console/receipts/response-routing-2026-09-18/README.md",
    "docs/acceptance/command-console/receipts/response-routing-2026-09-18/targeted-tests.log",
    "docs/acceptance/command-console/receipts/response-routing-2026-09-18/render-tests.log",
    "docs/acceptance/command-console/receipts/candidate-live-response-display-2026-09-18.md",
    "docs/acceptance/command-console/receipts/current-focused-native-2026-09-18.md",
    "docs/acceptance/command-console/receipts/native-rerun-locked-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-monitor-unplug-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-monitor-reconnect-2026-09-18.md",
    "docs/acceptance/command-console/receipts/candidate-monitor-auto-rehome-2026-09-18.md",
    "docs/acceptance/command-console/receipts/full-verification-2026-09-18.md",
    "docs/acceptance/adaptive-interface/receipts/candidate-atom-wave-2026-09-18.md",
)

MEMORY_ARTIFACTS = (
    "jarvis/memory.py",
    "jarvis/memory_extraction.py",
    "jarvis/memory_sweep.py",
    "jarvis/db.py",
    "jarvis/bot/pipeline.py",
    "jarvis/agents/supervisor.py",
    "jarvis/prompts.py",
    "jarvis/config.py",
    "jarvis/admin/server.py",
    "web/src/components/MemoryPanel.tsx",
    "jarvis/memory_model.py",
    "jarvis/memory_automation.py",
    "jarvis/memory_automation_eval.py",
    "tests/unit/test_memory_model.py",
    "tests/unit/test_memory_automation.py",
    "tests/unit/test_memory_automation_acceptance.py",
    "tests/unit/test_memory_rollout_acceptance.py",
    "tests/unit/test_memory.py",
    "tests/unit/test_memory_sweep.py",
    "tests/unit/test_memory_watcher.py",
    "tests/fixtures/memory_automation_cases.json",
    "tests/fixtures/memory_rollout_acceptance.json",
    "scripts/run_memory_provider_shadow.py",
    "scripts/run_memory_rollout_acceptance.py",
    "docs/acceptance/memory-automation/STATUS.md",
    "docs/acceptance/memory-automation/provider-shadow-receipt.json",
    "docs/acceptance/memory-automation/rollout-monitoring-receipt.json",
    "docs/acceptance/memory-automation/full-python-suite-2026-09-18.md",
)


def _missing(paths: tuple[str, ...]) -> list[str]:
    return [path for path in paths if not (ROOT / path).is_file()]


def test_command_console_manifest_artifacts_exist():
    assert not _missing(COMMAND_CONSOLE_ARTIFACTS)


def test_acceptance_runbook_exists():
    runbook = ROOT / "docs/acceptance/ACCEPTANCE_RUNBOOK.md"
    assert runbook.is_file()
    text = runbook.read_text(encoding="utf-8")
    for heading in (
        "## 2. Physical display recovery",
        "## 3. Live voice and response routing",
        "## 4. Sharing and accessibility",
        "## 5. Memory staged rollout",
        "## 6. Closure record",
    ):
        assert heading in text
    assert "ANTHROPIC_API_KEY=" not in text
    assert "OPENAI_API_KEY=" not in text
    assert "JARVIS_MEMORY_AUTOMATION_STAGE" in text


def test_consolidated_status_matrix_covers_both_plans_and_open_runtime_gates():
    status = (ROOT / "docs/acceptance/IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")
    for phrase in (
        "## Automated memory management",
        "## Command Center and Knowledge Atlas",
        "Mac staged enablement and benefit/cost observation",
        "voice-triggered repeat and provider/fetch evidence remain",
        "live picker/provider journey",
        "Five-day daily-driver acceptance",
    ):
        assert phrase in status


def test_memory_manifest_artifacts_exist():
    assert not _missing(MEMORY_ARTIFACTS)


def test_command_console_rendering_manifest_name_is_accounted_for():
    """The plan's requested suite exists under its landed, broader name."""
    plan = (ROOT / "docs/plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md").read_text(
        encoding="utf-8"
    )
    assert "CommandConsoleRenderingTests" in plan
    landed = ROOT / "macos/MortimerHost/Tests/MortimerHostTests/FullConsoleRenderingTests.swift"
    assert landed.is_file()
    source = landed.read_text(encoding="utf-8")
    assert "testCommandConsoleStartsInConversationWithVoiceControls" in source


def test_current_topology_receipt_is_two_screen_and_keeps_content_gate_open():
    receipt = ROOT / "docs/acceptance/command-console/receipts/display-topology-2026-09-18-current.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["screen_count"] == 2
    assert len(data["screens"]) == 2
    assert len({screen["display_id"] for screen in data["screens"]}) == 2
    assert "content-policy" in data["acceptance_effect"]
    assert "reconnect" in data["acceptance_effect"]


def test_current_external_stage_receipt_keeps_voice_and_reconnect_gates_open():
    receipt = ROOT / "docs/acceptance/command-console/receipts/candidate-external-stage-current-2026-09-18.md"
    text = receipt.read_text(encoding="utf-8")
    assert "Mortimer Display" in text
    assert "no fan-out" in text
    assert "ERROR VOICE" in text
    assert "remain open" in text
