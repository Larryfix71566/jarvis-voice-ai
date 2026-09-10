"""Compatibility responses for development tools retired by VM isolation.

These refusals are unconditional. A confirmed legacy action, missing sandbox
configuration, or unavailable sidecar must never re-enable a direct writer.
"""


def sandbox_required(*, application: bool = False) -> dict:
    if application:
        workflow = ["app_build_start", "app_build_status", "app_build_submit"]
        instruction = (
            "Use app_build_start for this change, including a single-file edit, "
            "then app_build_status and app_build_submit for the verified draft."
        )
    else:
        workflow = ["selfedit_start", "selfedit_write", "selfedit_finish"]
        instruction = (
            "Use selfedit_start to open the sandbox, selfedit_write to propose "
            "the change, and selfedit_finish to verify it and prepare a draft PR."
        )
    return {
        "ok": False,
        "code": "sandbox_required",
        "error": "Direct development writes have been retired. " + instruction,
        "replacement_tools": workflow,
    }
