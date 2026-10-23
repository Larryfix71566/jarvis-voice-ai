"""Read-only subscription retirement diagnostics; never run inference or auth."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jarvis.provider_access import access_mode
from jarvis.subscription import (
    CODEX_VERIFIED_VERSIONS, SubscriptionCapabilityError, codex_runtime_identity,
    resolve_provider_executable,
)
from jarvis.subscription_tools import CLAUDE_NATIVE_VERSIONS, claude_tool_runtime_identity


def retirement_readiness() -> dict[str, Any]:
    runtimes = {}
    for provider, inspect, versions in (
        ("claude", claude_tool_runtime_identity, CLAUDE_NATIVE_VERSIONS),
        ("codex", codex_runtime_identity, CODEX_VERIFIED_VERSIONS),
    ):
        selected = resolve_provider_executable(provider)
        entry: dict[str, Any] = {
            "installed_on_configured_path": selected is not None,
            "verified_versions": sorted(versions),
            "authentication": "not_checked", "billing": "not_verified",
            "capability_receipt": "not_validated_for_workload",
        }
        if selected:
            entry["executable"] = str(Path(selected).resolve())
            try:
                entry["identity"] = inspect()
                entry["runtime_contract"] = "known_version"
            except SubscriptionCapabilityError:
                entry["runtime_contract"] = "unverified"
        else:
            entry["runtime_contract"] = "unavailable"
        runtimes[provider] = entry
    return {
        "access_mode": access_mode(),
        "shared_routing_enabled": os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1",
        "subscription_text_enabled": os.environ.get("JARVIS_SUBSCRIPTION_TEXT_ENABLED") == "1",
        "activation_ready": False,
        "selective_api_policy": {
            "mode": "direct_apis_disabled",
            "direct_openai_anthropic_allowed": False,
            "openrouter": "explicit_canonical_endpoint_and_validated_approved_external_payload_only",
            "other_apis": "explicit_protected_registry_identity_and_validated_source_policy_only",
            "saygm": "pinned_endpoint_and_existing_catalog_privacy_authentication_budget_gates",
            "unknown_endpoint_allowed": False,
            "implicit_fallback_allowed": False,
            "legacy_unclassified_api_calls_allowed": False,
            "voice_restoration_verified": False,
        },
        "voice_adapter": {
            "implementation": "buffered_native_tool_bridge",
            "incremental_streaming_verified": False,
            "requires_host_classified_context": True,
            "source_provenance": "host_bound_monotonic_context",
            "production_activation_allowed": False,
        },
        "inference_attempts": 0,
        "runtimes": runtimes,
        "blockers": [
            "voice_subscription_streaming_and_tools_unverified",
            "exact_workload_runtime_capability_acceptance_required",
            "subscription_authentication_and_overage_settings_unverified",
            "protected_workloads_require_an_eligible_private_route",
            "integrated_release_acceptance_required",
        ],
    }
