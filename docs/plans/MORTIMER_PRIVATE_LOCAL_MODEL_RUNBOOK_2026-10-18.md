# Mortimer private local-model setup and integration runbook

**Date:** 2026-10-18 · **State:** instructions/design only; nothing installed or run.
**Parent:** [WS-27 enhancement plan](MORTIMER_ENHANCEMENT_IMPLEMENTATION_PLAN_2026-10-18.md)
· [sandbox evaluation](MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md).

Commands here are for a later explicitly authorized isolated setup. They are not
claims of successful execution, performance or permission to change this Mac.
Security settings, credentials, service installation and microphone grants need
explicit approval before execution. Production integration needs its own claim.

## 1. Hardware and candidate choice

The inventory supplied with Larry's request is an **M5 MacBook Air, Mac17,4,
10 CPU / 10 GPU cores, 16 GiB unified memory, macOS 27.0.1, about 143 GiB free**.
No Ollama, MLX, llama.cpp or LM Studio runtime was found in standard locations
in that inventory. This runbook does not repeat a device scan or infer a runtime
from Python availability. Roadmap mini examples are not Larry's actual hardware.

Recommend **Qwen3.5-4B Q4_K_M as the initial candidate**, Qwen3.5-9B Q4_K_M as
the quality challenger, and Ministral 3 8B as an independent comparison. This is
a sizing/experiment recommendation, not a measured winner or proof of fitness
for financial/email tasks. Official model/tag pages checked 2026-10-18:

| Candidate | Exact Ollama tag | Published size / short artifact ID |
|---|---|---|
| Initial | `qwen3.5:4b-q4_K_M` | ~3.3 GB · `d8b0f5e9760c` |
| Quality challenger | `qwen3.5:9b-q4_K_M` | ~6.6 GB · `56671c2ab938` |
| Independent challenger | `ministral-3:8b-instruct-2512-q4_K_M` | ~6.0 GB · `1922accd5827` |

Sources: [Qwen tags](https://ollama.com/library/qwen3.5/tags),
[exact 4B tag](https://ollama.com/library/qwen3.5:4b-q4_K_M),
[Qwen model card](https://huggingface.co/Qwen/Qwen3.5-4B),
[Ministral tags](https://ollama.com/library/ministral-3/tags) and
[official Ministral model card](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512).
Specific tags reduce ambiguity but are not immutable digest pins. Capture the
**full registry manifest digest and blob hashes** before admitting any acquired
artifact; check that its short ID matches the approved receipt. Stop on mismatch
and review the new manifest. Do not invent `model@sha256` pull syntax: the verified
commands below use official tag syntax plus a fail-closed artifact verification
step. Record runtime version/build, model license, quantization, template,
projector/assets and parameters in the receipt; freeze that local artifact for
the experiment and do not pull/update it midway.

Model file size is not runtime RAM. Weights, KV cache/context, projector,
runtime/Metal buffers, OS, Mortimer, STT and TTS share 16 GiB. Do not load the
advertised 256K context or a second LLM just because the file fits on disk.
Start with one loaded LLM, concurrency one, context at most 4096 tokens and a
bounded output/retrieval budget. Monitor memory pressure, swap growth, thermal
throttling and p95 voice response alongside Mortimer/speech in a separately
approved coexistence test. Stop and unload on pressure, sustained swap growth,
missed latency budgets or worker failure. A 9B model may fail that gate even when
it improves answers. No measured tokens/second or capacity result exists here.

## 2. Installation and isolated service — instructions only

### 2.1 Acquire and pin the runtime

Follow [official Ollama macOS installation](https://docs.ollama.com/macos):
obtain the official macOS DMG, verify its publisher/signature and record the
chosen release/version/hash, then place the app in an approved location.
The documentation supports Apple M-series and macOS 14 or newer; actual M5 and
model compatibility still need the smoke test. A standard installation uses
Applications and may request a CLI link. Do not approve links, background/login
startup or move prompts as part of this documentation. Choose a reviewed version
that advertises the exact model family and exposes the controls below; this plan
does not invent a tested minimum version. Retain the installer receipt for
reproducibility. Pin the experiment executable; review upgrades separately.

For a simple synthetic prototype, prefer a manually owned foreground server
with process-local environment, a dedicated model directory and no GUI/background
Ollama server running concurrently. Do not change `launchctl` or global settings
silently. Verify the executable and inspect `ollama serve --help` against the
recorded runtime first. Use a free loopback port selected/recorded by the later
sandbox design; `11434` below is the official default example, not a repository
port reservation. If occupied, stop and select an approved isolated port; never
kill an unknown listener.

### 2.2 Disable cloud and bound resources

The following future prototype example assumes `ollama` resolves to the reviewed
binary and the later sandbox has approved this directory/unused loopback port:

```sh
mkdir -p "$PWD/local-model-sandbox/models"
OLLAMA_NO_CLOUD=1 \
OLLAMA_HOST=127.0.0.1:11434 \
OLLAMA_MODELS="$PWD/local-model-sandbox/models" \
OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_QUEUE=4 \
OLLAMA_CONTEXT_LENGTH=4096 \
OLLAMA_KEEP_ALIVE=60s \
ollama serve
```

These are runtime vendor settings, not newly reserved `JARVIS_*` keys. Official
[FAQ](https://docs.ollama.com/faq) documents local-only `OLLAMA_NO_CLOUD=1`, default
loopback binding, context, lifecycle and concurrency. An alternative persistent
configuration is `"disable_ollama_cloud": true` merged into `~/.ollama/server.json`;
that is a separate approved settings change, not a command to overwrite existing
configuration. Verify the started process reports cloud disabled and the bind
is loopback only; unknown/ignored settings fail the privacy gate. Do not sign in
to cloud, use `:cloud` models, web search, tunnels, `0.0.0.0` or widened origins.

Downloads need public registry access during acquisition. Local-only cloud
settings do **not** prove network egress isolation: after assets are acquired,
apply the separately approved process/VM egress policy and test it with synthetic
requests. Localhost is neither authentication nor isolation from other local
processes. A fake OpenAI API key is not access control.

### 2.3 Pull, inspect, freeze and run exact candidates

In a second terminal pointed to that isolated server, commands from the official
[CLI reference](https://docs.ollama.com/cli) and model pages are:

```sh
export OLLAMA_HOST=127.0.0.1:11434
ollama --version
ollama pull qwen3.5:4b-q4_K_M
ollama ls
ollama show qwen3.5:4b-q4_K_M
```

**Mandatory gate before the next command:** compare the acquired manifest's full
digest/blob hashes, quantization and short ID against the reviewed asset receipt.
Inspect the manifest in the dedicated model directory and record SHA-256s using
a read-only artifact-inventory step; the public page's short ID alone is not an
integrity verification. Approve the full manifest once acquired before inference
or private integration. If it changed since this runbook, stop for re-review.
Use no unverified “latest” alias or automatic re-pull during the experiment.

```sh
ollama run qwen3.5:4b-q4_K_M "Reply with a short greeting using synthetic data only."
ollama ps
ollama stop qwen3.5:4b-q4_K_M
```

Acquire challengers only within approved disk/bandwidth/setup scope, with the
same verification gate; evaluate serially after stopping the previous LLM:

```sh
ollama pull qwen3.5:9b-q4_K_M
ollama show qwen3.5:9b-q4_K_M
# Verify/approve the acquired full manifest before run.
ollama run qwen3.5:9b-q4_K_M "Reply with a short greeting using synthetic data only."
ollama stop qwen3.5:9b-q4_K_M
ollama pull ministral-3:8b-instruct-2512-q4_K_M
ollama show ministral-3:8b-instruct-2512-q4_K_M
# Verify/approve the acquired full manifest before run.
ollama run ministral-3:8b-instruct-2512-q4_K_M "Reply with a short greeting using synthetic data only."
ollama stop ministral-3:8b-instruct-2512-q4_K_M
```

These exact **tag-pinned** pull/run commands are verified syntax, not a claim of
immutable registry names or tested execution. Run only the approved frozen local
artifact after digest verification. Disable network after acquisition for private
synthetic testing, including model/tokenizer downloads and automatic updates.
Bound startup, per-call deadline, queue length and output tokens in the host;
unload via `ollama stop` after a session, or use API `keep_alive: 0` when done.
Changing process settings alone does not prove deadline/cancellation propagation.

## 3. Structured output, retrieval and arithmetic prototype

Use [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
on local `/api/chat` with an explicit schema. Host code must parse/validate output,
source IDs, bounds and permitted actions; schema-conforming JSON is not factual
proof. This synthetic example uses documented request fields and is **unexecuted**:

```sh
curl --fail http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"qwen3.5:4b-q4_K_M",
    "messages":[{"role":"user","content":"Synthetic source S1: appointment is Tuesday. Return source_ids [S1] and abstain false."}],
    "stream":false,
    "keep_alive":0,
    "options":{"num_ctx":4096,"num_predict":256},
    "format":{
      "type":"object",
      "properties":{"source_ids":{"type":"array","items":{"type":"string"}},"abstain":{"type":"boolean"}},
      "required":["source_ids","abstain"],
      "additionalProperties":false
    }
  }'
```

This is a wire-shape smoke test, not a complete privacy/quality gate. Validate
response JSON twice: API envelope then model content; unknown source IDs refuse.
Test tools, streaming, cancellation, malformed/incomplete output and reasoning
separation for the pinned runtime/model/template. Do not strip thinking tokens
with brittle string patterns or forward hidden reasoning into speech/logs.

Retrieval implementation tasks, after dispatch:

1. Use existing admitted storage/source identity and private read-only capability.
   Start with deterministic local full-text/metadata search; if embeddings are
   needed, acquire a separately reviewed local embedding model and account for
   its memory/egress. No cloud vectorizer or ordinary KB digest of private data.
2. Limit retrieval to the exact authorized account/thread/date/document scope;
   initial budget ≤4 snippets and ≤2000 input tokens within total 4096, with
   source IDs/versions and explicit partial/omitted indicators. Reserve output
   room; truncate at source boundaries, never pretend omitted data was searched.
3. Delimit untrusted records; model proposes typed extraction/answer plus sources
   and abstention. Host checks retrieval scope, access, evidence and destination.
   Documents/email cannot grant tools, authorize writes or downgrade privacy.
4. Parse amounts/dates/currencies into typed values and use Decimal/cents in
   deterministic code. Keep source-row links, rounding rules and as-of dates.
   Missing/conflicting data yields abstention/reconciliation, never guessed math.
5. Preserve encrypted finance user-presence access and turn expiry. No background
   decrypt, automatic trading/transfers, mail sends or calendar/commitment writes.

## 4. Mortimer integration — missing route and production isolation

At main `28420af`, [model access](../../config/model_access.yaml) declares local
policy; [model_routing.py](../../jarvis/model_routing.py) sync and async route
factories explicitly raise `local model runtime is not configured`.
Changing a URL or setting a profile cannot make that a supported private route.
The [platform local plan](MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md)'s generic endpoint
example is not proof of integration with the newer policy-aware execution path.

After synthetic prototype proof, a separately claimed WS-05-compatible slice
must implement a provider boundary that preserves source classification,
capabilities, privacy, budgets, timeout/cancel behavior, per-run identity,
structured outputs, tools/stream framing and error redaction. Reuse the existing
model registry/resolver and provider-neutral execution; never a second model
catalog or direct-call bypass. Treat local model identity/endpoint pins as
reviewed configuration; respect existing model floors. Any explicit lower-tier
local-private workload exception needs Larry's decision and validation, rather
than silently lowering all specialists' Sonnet-or-better floor.

Host-owned private labels propagate from capture/source through retrieval,
model execution, results, memory admission, artifacts and all sinks. Bind the
route before recording; default finance to typed input/text-only output until
fully local speech passes. Reject remote/redirect/proxy endpoints, cloud model
tags, implicit fallback and mixed private/public history. A timeout/overload/missing
runtime means private work is unavailable, not permission to call a cloud model.
Public weather/research can retain its approved cloud route in a separate scope.

**Developer prototype versus production:** foreground localhost with synthetic
fixtures is useful but insufficient. Before records, review service user and
filesystem permissions, authenticated broker/IPC or appropriate local access
control, explicit egress restrictions, no cloud credentials in local workers,
encrypted user-presence storage, ephemeral per-turn buffers, log/cache/history
retention, backups/crash telemetry and device protection. Restrict model tools
and source paths. Authenticate caller and task/privacy authority outside the LLM;
protect against other local users/processes and hostile retrieved content.
Any actual security-setting, entitlement, firewall or credential grant requires
explicit approval. Do not bypass existing sandbox protections to obtain GPU/audio.

Local private finance on this Air also needs explicit reconciliation of the
older mini/G3 gate, as described in the parent plan. Local hardware proof is not
automatic finance activation. Reconcile T3.4/R7/T4b's old private ElevenLabs
residual: private output uses local TTS or text, never cloud by default.

## 5. Optional fully local speech assets

Local STT and TTS are separate from Ollama. The official
[MLX Whisper example README](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
([raw README](https://raw.githubusercontent.com/ml-explore/mlx-examples/main/whisper/README.md))
documents `ffmpeg`, `pip install mlx-whisper`, the `mlx_whisper` CLI and
`mlx_whisper.transcribe`. A later setup should use a dedicated environment,
pinned package lock and reviewed model snapshot instead of unversioned installs.
Do not execute the README setup as part of this task. Acquire the selected
Whisper weights/tokenizer in the download phase, record hashes and pass a local
path to `path_or_hf_repo` so private transcription cannot trigger a download.
The example is batch transcription; streaming buffers/end-of-turn, correction,
barge-in and cancellation need an implemented/tested adapter.

[Kokoro-82M's official model card](https://huggingface.co/hexgrad/Kokoro-82M)
identifies the TTS model and usage dependencies. Pin its package/model revision,
voice assets, phonemizer/espeak dependencies and license separately. Use only
reviewed local assets/voices and local output; do not allow an implicit download
or remote TTS fallback. No claim that 82M parameters specifies total resident
memory or latency. Test intelligibility/names/numbers, first-useful-audio p50/p95,
chunk seams, interruption stop, audio cleanup and memory/thermal load with the
chosen LLM plus Mortimer. A 9B LLM + Whisper + Kokoro may exceed practical 16-GiB
headroom; reduce model/context or stay text-only based on measurements.

Select private mode before mic capture; enforce a separate audio path, local
STT/TTS, no cloud prebuffer/wake transcription and no private audio written to
ordinary recordings/history. Clear temporary audio/transcripts on cancel/session
end according to the approved retention policy. The public Flux/ElevenLabs route
must not receive private speech while mode negotiation or local initialization
is pending. A spoken “use private mode” after cloud recording began is too late.

## 6. Test matrix and release gates

All tests below are proposed, synthetic and initially isolated. No private user
records or paid tests were executed for this runbook.

| Area | Required proof / negative tests |
|---|---|
| Artifact/runtime | Version/hash/manifest/quant/template match; changed tag/blob or unsupported model refuses; frozen assets work without downloads. |
| Resource/lifecycle | Cold/warm load, bounded queue/concurrency/context/output/deadlines, cancellation/drain/unload; no second LLM; memory pressure/swap/thermal and simultaneous speech/Mortimer effects measured. |
| Route isolation | Remote URL/redirect/proxy/cloud tag, missing daemon, timeout, unsupported feature, overload and retry all fail closed with no cloud call. |
| Privacy sinks | Synthetic private canaries absent from external STT/TTS/LLM, ordinary memory/digest/history/logs/errors/notifications/caches/backups/tool results; packet/process capture proves no inference-time egress. |
| Capture/output | Mode chosen before audio, initialization/failure/cancel cannot leak prebuffer; local TTS or text only. Measure actual playback, not server audio arrival. |
| Retrieval/quality | Exact thread/document/source/version, bounded context/partial disclosure, contradictory/missing source abstention, correction/provenance; compare all three models on same sealed synthetic cases. |
| Arithmetic | Decimal/cents rounding, currencies/dates/negative values/duplicate records/reconciliation; source-backed totals match deterministic oracle; LLM arithmetic cannot override it. |
| Injection/authority | Hostile email/attachment/document cannot grant tools, exfiltrate other records, edit source or authorize calendar/mail/financial writes. |
| Encrypted tier | User presence required, locked/expired/foreign-task access refuses, no background decrypted persistence; crash/restart cannot recover unapproved plaintext. |
| Contract | Sync/async route parity, structured output/tool framing, malformed stream, retry/cancel races, exact model identity and content-free diagnostics. |

Exit to any real-data pilot requires independent review, applicable existing
acceptance closure, approved production isolation/retention and explicit Larry
scope. Record objective quality/reliability, p50/p95 latency, maximum memory and
coexistence evidence; no catalog reputation substitutes. If a local candidate
cannot meet the task, abstain and retain text-only/manual analysis; never send
records to cloud to complete the comparison.

## 7. Rollback and removal without deleting records

For a sandbox prototype, cancel/fence owned requests, close the client, unload
with `ollama stop <exact-tag>` and stop the owned foreground server. Confirm it
no longer listens. Preserve source records, encrypted stores, task/checkpoint
history and evidence. For a later production pilot, disable admission to its
private route, restore reviewed app/config through the existing release process,
and leave private work unavailable/text-only until a safe local route is ready.
No cloud fallback.

Only after separate removal approval, `ollama rm <exact-tag>` removes a selected
model from the explicitly selected isolated server/store. Inventory shared blobs
and other users/models first. Remove a dedicated prototype runtime/environment
only after reviewing its exact paths and retained receipts. Do not use broad
`rm -rf ~/.ollama`, delete records, wipe the Keychain or uninstall unrelated
assets. Use official uninstall guidance as a reference, not blanket deletion
permission. Stop services before any approved artifact removal.

2026-10-18 progress: official tag sizes/IDs and command shapes checked; no local
runtime, model, STT/TTS assets, private route or benchmark results installed/tested.
