#!/usr/bin/env python3
"""Inspect the installed Codex tool surface with a loopback mock, no inference.

This records a capability receipt; it does not set a gate, change a route, read
tokens, test account access, or establish subscription billing. Model metadata
comes from the installed executable and is embedded in the receipt.
"""
from __future__ import annotations

import argparse
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.subscription import (
    SubscriptionRuntimeError,
    _canonical_json,
    _codex_argv,
    _codex_text,
    _json_digest,
    _run_sync,
    codex_runtime_identity,
)

PROBE_TOKEN = "MORTIMER_LOCAL_CAPABILITY_FIXTURE_OK"
NEGATIVE_CALL_ID = "call_unadvertised_fixture"
NEGATIVE_TOOL_NAME = "exec_command"


def installed_host_refusal(payload: Any) -> bool:
    """Exact 0.160.0 native response; never print/retain a request or output.

    The installed binary contains the public `unsupported call: ` literal.
    Its matching-call function output is an explicit host refusal even when
    the model safely recovers to a terminal text answer afterwards.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), list):
        return False
    matches = [item for item in payload["input"] if isinstance(item, dict)
               and item.get("type") == "function_call_output"
               and item.get("call_id") == NEGATIVE_CALL_ID]
    return len(matches) == 1 and matches[0].get("output") == f"unsupported call: {NEGATIVE_TOOL_NAME}"


def bundled_catalog(executable: str, model: str) -> dict[str, Any]:
    """Read public, compiled-in model metadata; never a user cache/auth file."""
    binary = Path(executable).read_bytes()
    marker = b'{\n  "models": ['
    start = binary.find(marker)
    if start < 0:
        raise ValueError("installed executable has no supported bundled catalog")
    catalog, _ = json.JSONDecoder().raw_decode(
        binary[start:start + 2_000_000].decode("utf-8", errors="replace")
    )
    matches = [entry for entry in catalog.get("models", [])
               if isinstance(entry, dict) and entry.get("slug") == model]
    if len(matches) != 1:
        raise ValueError("requested exact model is absent or ambiguous in the bundled catalog")
    return {"models": matches}


def probe(model: str, *, timeout: float = 30, negative: bool = False) -> dict[str, Any]:
    identity = codex_runtime_identity()
    catalog = bundled_catalog(identity["path"], model)
    requests: list[dict[str, Any]] = []
    canary_directory = tempfile.TemporaryDirectory(prefix="mortimer-no-tool-canary-", dir="/tmp")
    canary = Path(canary_directory.name) / "unexpected-side-effect"

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass

        def do_GET(self) -> None:
            requests.append({"unexpected_path": True})
            self.send_error(403, "only a local Responses request is allowed")

        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 2_000_000 or self.headers.get("Content-Encoding"):
                requests.append({"unexpected_encoding_or_size": True})
                self.send_error(413)
                return
            try:
                payload = json.loads(self.rfile.read(size))
            except (ValueError, TypeError):
                requests.append({"malformed_payload": True})
                self.send_error(400)
                return
            row = {"tools": payload.get("tools", []),
                   "api_credentials_absent": not bool(self.headers.get("Authorization")),
                   "model_matches": payload.get("model") == model,
                   "path_matches": self.path == "/v1/responses",
                   "explicit_matching_host_refusal": installed_host_refusal(payload)}
            requests.append(row)
            if (row["tools"] != [] or not row["api_credentials_absent"]
                    or not row["model_matches"] or not row["path_matches"]):
                self.send_error(403, "fixture rejects every tool, credential or unexpected route")
                return
            message = {"id": "msg_mortimer_fixture", "type": "message", "status": "completed",
                       "role": "assistant", "content": [{"type": "output_text",
                       "text": PROBE_TOKEN, "annotations": []}]}
            if negative and len(requests) == 1:
                message = {"id": "fc_unadvertised_fixture", "type": "function_call",
                           "call_id": NEGATIVE_CALL_ID, "name": NEGATIVE_TOOL_NAME,
                           "arguments": json.dumps({"cmd": f"touch {canary}"}), "status": "completed"}
            response = {"id": "resp_mortimer_fixture", "object": "response",
                        "status": "completed", "model": model, "output": [message],
                        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
            events = [
                {"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
                {"type": "response.output_item.added", "output_index": 0,
                 "item": {**message, "status": "in_progress"}},
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": response},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: "
                                  + _canonical_json(event) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    invocation = _codex_argv(model, command=identity["path"])
    argv = invocation[:-1]
    transport = {
        "model_provider": "mortimer_capability_fixture",
        "model_providers.mortimer_capability_fixture.name": "Mortimer loopback fixture",
        "model_providers.mortimer_capability_fixture.base_url": f"http://127.0.0.1:{server.server_port}/v1",
        "model_providers.mortimer_capability_fixture.wire_api": "responses",
        "model_providers.mortimer_capability_fixture.requires_openai_auth": False,
        "model_providers.mortimer_capability_fixture.request_max_retries": 0,
        "model_providers.mortimer_capability_fixture.stream_max_retries": 0,
        "model_providers.mortimer_capability_fixture.supports_websockets": False,
    }
    for name, value in transport.items():
        argv.extend(["-c", name + "=" + _canonical_json(value)])
    argv.append("-")
    success = False
    error_category = None
    try:
        stdout = _run_sync(argv, f"Reply with exactly {PROBE_TOKEN} and use no tools.",
                           timeout, provider="Codex capability fixture", catalog=catalog)
        success = _codex_text(stdout) == PROBE_TOKEN
    except SubscriptionRuntimeError as exc:
        error_category = exc.category
    finally:
        server.shutdown()
        server.server_close()
    valid_request = len(requests) == 1 and requests[0].get("tools") == []
    if negative:
        valid_request = len(requests) == 2 and all(row.get("tools") == []
            and row.get("api_credentials_absent") is True and row.get("model_matches") is True
            and row.get("path_matches") is True for row in requests)
    credential_absent = valid_request and all(row.get("api_credentials_absent") is True for row in requests)
    explicit_refusal = negative and valid_request and requests[1].get("explicit_matching_host_refusal") is True
    side_effect_absent = not canary.exists()
    canary_directory.cleanup()
    return {
        "schema_version": 1, "runtime": "codex", "model": model,
        "executable": identity, "proof_kind": "installed_cli_loopback_mock",
        "catalog": catalog, "catalog_sha256": _json_digest(catalog),
        "invocation_sha256": _json_digest(invocation),
        "advertised_tools": [] if valid_request else None,
        "terminal_success_without_error_items": success and valid_request,
        "api_credentials_absent": credential_absent, "real_provider_calls": 0,
        "provider_inference_performed": False, "request_count": len(requests),
        "error_category": error_category,
        "negative_unadvertised_tool_rejected": bool(explicit_refusal and side_effect_absent),
        "explicit_matching_host_refusal": bool(explicit_refusal),
        "side_effect_absent": side_effect_absent,
        "limits": ["Local tool construction/parser evidence only.",
                   "No subscription account, model inference, allowance, overage or billing acceptance.",
                   "An explicit operator gate and matching binary/model/config/catalog are still required."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("timeout must be from 1 to 60 seconds")
    receipt = probe(args.model, timeout=args.timeout)
    negative = probe(args.model, timeout=args.timeout, negative=True)
    receipt["negative_unadvertised_tool_rejected"] = negative["negative_unadvertised_tool_rejected"]
    receipt["negative_probe"] = {key: negative[key] for key in (
        "negative_unadvertised_tool_rejected", "explicit_matching_host_refusal",
        "side_effect_absent", "terminal_success_without_error_items", "error_category", "request_count")}
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runtime": receipt["executable"]["version"],
                      "model": args.model, "no_tools_observed": receipt["advertised_tools"] == [],
                      "terminal_success": receipt["terminal_success_without_error_items"],
                      "real_provider_calls": 0}))
    return 0 if receipt["terminal_success_without_error_items"] and receipt["negative_unadvertised_tool_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
