import base64
import pytest
from hashlib import sha256

import asyncio
from jarvis.bot.shared_content import (normalize_message, normalize_shared_content,
                                       approve_transfer, SharedContentService,
                                       validate_input_message, build_shared_content_tool,
                                       parse_voice_consent)
from jarvis.bot.shared_content_transfer import SharedContentTransferSession
from jarvis.bot.sensitive_turn import SensitiveTurn


def test_text_normalization_is_bounded_and_strips_controls():
    item = normalize_shared_content(kind="text", text=" hello\x00 world ")
    assert item.text == "hello world" and item.ephemeral and item.digest
    with pytest.raises(ValueError):
        normalize_shared_content(kind="text", text="x" * 12_001)


def test_image_requires_allowlisted_type_and_never_accepts_a_path():
    item = normalize_message({"kind": "image", "mime_type": "image/png",
                              "data_base64": base64.b64encode(b"png").decode()})
    assert item.data == b"png"
    with pytest.raises(ValueError):
        normalize_message({"kind": "image", "data_base64": "not-base64"})
    with pytest.raises(ValueError):
        normalize_shared_content(kind="image", data=b"x", mime_type="image/svg+xml")


def test_transfer_requires_explicit_approval_and_provider_disclosure():
    item = normalize_shared_content(kind="text", text="research")
    assert approve_transfer(item, approved=False)["status"] == "cancelled"
    with pytest.raises(ValueError):
        approve_transfer(item, approved=True)
    result = approve_transfer(item, approved=True, provider="openai")
    assert result["status"] == "approved" and result["ephemeral"]


def test_service_requires_approval_caches_result_and_clears_items():
    item = normalize_shared_content(kind="text", text="evidence")
    calls = []
    service = SharedContentService(model=lambda items, question: calls.append(question) or "answer")
    service.stage(item)
    request = lambda: service.analyze("req-1", "batch-1", [item.content_id], "What?", "approval-1")
    result = asyncio.run(request())
    assert result["ok"] and result["ephemeral"] and calls == ["What?"]
    replay = asyncio.run(request())
    assert replay == result and calls == ["What?"]
    denied = asyncio.run(service.analyze("req-2", "batch-1", [item.content_id], "What?", "approval-2"))
    assert denied["error_code"] == "decode_failed"


def test_input_protocol_is_strict_and_bounded():
    batch = "00000000-0000-4000-8000-000000000001"
    attachment = "00000000-0000-4000-8000-000000000002"
    message = validate_input_message({
        "type": "input/analyze", "batch_id": batch,
        "attachment_ids": [attachment], "question": "Summarize this",
    })
    assert message["attachment_ids"] == [attachment]
    with pytest.raises(ValueError):
        validate_input_message({**message, "unexpected": True})
    with pytest.raises(ValueError):
        validate_input_message({**message, "question": "x" * 2001})


def test_voice_shared_content_only_requests_an_explicit_offer():
    sent = []

    async def push(message):
        sent.append(message)

    _, handler = build_shared_content_tool(
        push,
        session_id="00000000-0000-4000-8000-000000000001",
        generation="00000000-0000-4000-8000-000000000002",
        profile={"id": "vision", "label": "Configured vision"},
    )
    attachment = "00000000-0000-4000-8000-000000000003"
    result = asyncio.run(handler({"attachment_ids": [attachment], "question": "Compare these."}))
    assert "approval" in result.lower()
    assert sent[0]["type"] == "input/offer"
    assert sent[0]["attachment_ids"] == [attachment]
    assert sent[0]["profile"]["label"] == "Configured vision"


def test_voice_consent_accepts_only_the_exact_pending_notice_phrases():
    assert parse_voice_consent("Send these items!") is True
    assert parse_voice_consent(" cancel   these items ") is False
    assert parse_voice_consent("send the items") is None
    assert parse_voice_consent("Send these items and then summarize") is None


def test_server_only_offer_cannot_be_used_as_client_approval():
    transfer = SharedContentTransferSession(SharedContentService())
    result = transfer.handle({
        "type": "input/offer", "version": 1,
        "session_id": "00000000-0000-4000-8000-000000000001",
        "generation": "00000000-0000-4000-8000-000000000002",
        "request_id": "00000000-0000-4000-8000-000000000003",
        "batch_id": "00000000-0000-4000-8000-000000000004",
        "attachment_ids": ["00000000-0000-4000-8000-000000000005"],
        "question": "Explain.", "profile": {"id": "vision", "label": "Configured vision"},
    })
    assert result["status"] == "error" and result["code"] == "server_only_message"


def test_input_offer_and_chunk_accept_common_versioned_envelope():
    batch = "00000000-0000-4000-8000-000000000010"
    attachment = "00000000-0000-4000-8000-000000000011"
    envelope = {
        "version": 1,
        "session_id": "00000000-0000-4000-8000-000000000012",
        "generation": "00000000-0000-4000-8000-000000000013",
        "request_id": "00000000-0000-4000-8000-000000000014",
    }
    offer = validate_input_message({
        "type": "input/offer", "batch_id": batch,
        "attachment_ids": [attachment], "question": "Explain this.",
        "profile": {"id": "vision", "label": "Configured vision"}, **envelope,
    })
    assert offer["version"] == 1 and offer["request_id"] == envelope["request_id"]
    chunk = validate_input_message({
        "type": "input/chunk", "transfer_id": batch,
        "attachment_id": attachment, "sequence": 0,
        "base64": base64.b64encode(b"chunk").decode(), **envelope,
    })
    assert chunk["attachment_id"] == attachment


def test_approved_manifest_chunks_commit_and_analyze_are_ephemeral():
    batch = "00000000-0000-4000-8000-000000000020"
    approval = "00000000-0000-4000-8000-000000000021"
    attachment = "00000000-0000-4000-8000-000000000022"
    session_id = "00000000-0000-4000-8000-000000000023"
    generation = "00000000-0000-4000-8000-000000000024"
    raw = b"approved research"
    digest = sha256(raw).hexdigest()
    calls = []
    service = SharedContentService(model=lambda items, question: calls.append((len(items), question)) or "answer")
    transfer = SharedContentTransferSession(service, session_id=session_id, generation=generation)
    envelope = {"version": 1, "session_id": session_id, "generation": generation,
                "request_id": "00000000-0000-4000-8000-000000000026"}
    accepted = transfer.handle({**envelope, "type": "input/manifest", "batch_id": batch,
                                "approval_id": approval, "question": "Explain this.",
                                "attachments": [{"content_id": attachment, "kind": "text",
                                                 "mime_type": "text/plain", "digest": digest,
                                                 "total_bytes": len(raw)}]})
    assert accepted["type"] == "input/accept" and accepted["code"] == "transfer_accepted"
    transfer_id = accepted["transfer_id"]
    encoded = base64.b64encode(raw).decode()
    assert transfer.handle({**envelope, "type": "input/chunk", "transfer_id": transfer_id,
                            "attachment_id": attachment, "sequence": 0, "base64": encoded})["status"] == "ok"
    assert transfer.handle({**envelope, "type": "input/commit", "transfer_id": transfer_id,
                            "attachment_id": attachment, "total_chunks": 1,
                            "total_bytes": len(raw), "sha256": digest})["type"] == "input/ready"
    result = asyncio.run(transfer.analyze({**envelope, "type": "input/analyze", "batch_id": batch,
                                           "attachment_ids": [attachment], "question": "Explain this.",
                                           "request_id": "00000000-0000-4000-8000-000000000025"}))
    assert result["status"] == "ok" and result["data"]["answer"] == "answer"
    assert calls == [(1, "Explain this.")] and transfer.batch_id is None


def test_staging_does_not_pause_memory_but_approved_manifest_does():
    """Imported bytes stay outside memory until the approved transfer boundary."""
    holder = SensitiveTurn()
    service = SharedContentService()
    staged = normalize_shared_content(kind="text", text="private source")
    service.stage(staged)
    assert holder.is_armed() is False

    session_id = "00000000-0000-4000-8000-000000000060"
    generation = "00000000-0000-4000-8000-000000000061"
    transfer = SharedContentTransferSession(service, session_id=session_id,
                                             generation=generation,
                                             sensitive_turn=holder)
    accepted = transfer.handle({
        "type": "input/manifest", "version": 1,
        "session_id": session_id, "generation": generation,
        "request_id": "00000000-0000-4000-8000-000000000062",
        "batch_id": "00000000-0000-4000-8000-000000000063",
        "approval_id": "00000000-0000-4000-8000-000000000064",
        "question": "Explain this.",
        "attachments": [{
            "content_id": str(staged.content_id), "kind": "text",
            "mime_type": staged.mime_type, "digest": staged.digest,
            "total_bytes": len((staged.text or "").encode("utf-8")),
        }],
    })
    assert accepted["type"] == "input/accept"
    assert holder.is_armed() is True


def test_transfer_rejects_reordered_duplicate_chunks_and_digest_mismatch():
    batch = "00000000-0000-4000-8000-000000000030"
    attachment = "00000000-0000-4000-8000-000000000031"
    common = {"version": 1, "session_id": "00000000-0000-4000-8000-000000000032",
              "generation": "00000000-0000-4000-8000-000000000033",
              "request_id": "00000000-0000-4000-8000-000000000035"}
    raw = b"x"
    service = SharedContentService(model=lambda *_: "unused")
    transfer = SharedContentTransferSession(service, session_id=common["session_id"], generation=common["generation"])
    digest = sha256(raw).hexdigest()
    accepted = transfer.handle({**common, "type": "input/manifest", "batch_id": batch,
                                "approval_id": "00000000-0000-4000-8000-000000000034",
                                "attachments": [{"content_id": attachment, "kind": "text", "mime_type": "text/plain",
                                                  "digest": digest, "total_bytes": 1}]})
    transfer_id = accepted["transfer_id"]
    encoded = base64.b64encode(raw).decode()
    assert transfer.handle({**common, "type": "input/chunk", "transfer_id": transfer_id,
                            "attachment_id": attachment, "sequence": 1, "base64": encoded})["status"] == "error"
    assert transfer.handle({**common, "type": "input/chunk", "transfer_id": transfer_id,
                            "attachment_id": attachment, "sequence": 0, "base64": encoded})["status"] == "ok"
    assert transfer.handle({**common, "type": "input/commit", "transfer_id": transfer_id,
                            "attachment_id": attachment, "total_chunks": 1, "total_bytes": 1,
                            "sha256": "0" * 64})["status"] == "error"


def test_manifest_metadata_is_strict_and_cancel_clears_state():
    batch = "00000000-0000-4000-8000-000000000040"
    common = {"version": 1, "session_id": "00000000-0000-4000-8000-000000000041",
              "generation": "00000000-0000-4000-8000-000000000042",
              "request_id": "00000000-0000-4000-8000-000000000045"}
    transfer = SharedContentTransferSession(SharedContentService(), session_id=common["session_id"], generation=common["generation"])
    bad = {**common, "type": "input/manifest", "batch_id": batch,
           "approval_id": "00000000-0000-4000-8000-000000000043", "attachments": [{
               "content_id": "00000000-0000-4000-8000-000000000044", "kind": "text",
               "mime_type": "text/plain", "digest": "bad", "total_bytes": 1}]}
    assert transfer.handle(bad)["status"] == "error"
    assert transfer.handle({**common, "type": "input/cancel", "batch_id": batch})["status"] == "cancelled"
    assert transfer.batch_id is None


def test_cancel_during_analysis_discards_late_provider_result():
    batch = "00000000-0000-4000-8000-000000000050"
    attachment = "00000000-0000-4000-8000-000000000051"
    session_id = "00000000-0000-4000-8000-000000000052"
    generation = "00000000-0000-4000-8000-000000000053"
    approval = "00000000-0000-4000-8000-000000000054"
    request_id = "00000000-0000-4000-8000-000000000055"
    raw = b"cancel me"
    digest = sha256(raw).hexdigest()
    started = asyncio.Event()
    release = asyncio.Event()

    async def model(items, question):
        started.set()
        await release.wait()
        return "late answer"

    service = SharedContentService(model=model)
    transfer = SharedContentTransferSession(service, session_id=session_id, generation=generation)
    common = {"version": 1, "session_id": session_id, "generation": generation,
              "request_id": "00000000-0000-4000-8000-000000000056"}
    accepted = transfer.handle({**common, "type": "input/manifest", "batch_id": batch,
                                "approval_id": approval, "question": "Explain.", "attachments": [{
                                    "content_id": attachment, "kind": "text", "mime_type": "text/plain",
                                    "digest": digest, "total_bytes": len(raw)}]})
    transfer_id = accepted["transfer_id"]
    transfer.handle({**common, "type": "input/chunk", "transfer_id": transfer_id,
                     "attachment_id": attachment, "sequence": 0,
                     "base64": base64.b64encode(raw).decode()})
    transfer.handle({**common, "type": "input/commit", "transfer_id": transfer_id,
                     "attachment_id": attachment, "total_chunks": 1, "total_bytes": len(raw),
                     "sha256": digest})

    async def run():
        task = asyncio.create_task(transfer.analyze({**common, "type": "input/analyze", "batch_id": batch,
                                                     "attachment_ids": [attachment], "question": "Explain.",
                                                     "request_id": request_id}))
        await started.wait()
        transfer.handle({**common, "type": "input/cancel", "batch_id": batch})
        release.set()
        return await task

    result = asyncio.run(run())
    assert result["status"] == "error" and result["code"] == "cancelled"


def test_malformed_analyze_is_reported_without_escaping_the_session():
    transfer = SharedContentTransferSession(SharedContentService())
    result = asyncio.run(transfer.analyze({"type": "input/analyze", "version": 1,
                                           "batch_id": "bad", "attachment_ids": [],
                                           "question": ""}))
    assert result["status"] == "error" and result["code"] == "invalid_input"
