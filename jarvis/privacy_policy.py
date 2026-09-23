"""Local data-policy checks performed before model/tool transmission."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from jarvis.model_routing import AccessRoute, ModelRouteError


class PrivacyLevel(IntEnum):
    APPROVED_EXTERNAL = 1
    CONFIDENTIAL = 2
    LOCAL_ONLY = 3


_NAMES = {
    "approved_external": PrivacyLevel.APPROVED_EXTERNAL,
    "confidential": PrivacyLevel.CONFIDENTIAL,
    "local_only": PrivacyLevel.LOCAL_ONLY,
}


@dataclass(frozen=True)
class DataPolicy:
    level: str = "confidential"
    source: str = "unlabeled"

    def __post_init__(self) -> None:
        if self.level not in _NAMES:
            raise ValueError(f"unknown privacy level {self.level!r}")


def strictest(*policies: DataPolicy) -> DataPolicy:
    if not policies:
        return DataPolicy()
    selected = max(policies, key=lambda item: _NAMES[item.level])
    return DataPolicy(selected.level, "+".join(item.source for item in policies))


def assert_route_allowed(route: AccessRoute, policy: DataPolicy) -> None:
    """Raise before transmission when a route is less private than required."""
    required = _NAMES[policy.level]
    offered = _NAMES.get(route.privacy)
    if offered is None or offered < required:
        raise ModelRouteError(
            f"route {route.name!r} provides {route.privacy!r}, "
            f"but {policy.source} requires {policy.level!r}"
        )


def inherit_result_policy(input_policy: DataPolicy, *, source: str = "result") -> DataPolicy:
    """Model output/tool result retains the strictest input restriction."""
    return DataPolicy(input_policy.level, source)

