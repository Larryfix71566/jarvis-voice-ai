# Interactive memory graph progress

Status: implemented in the adaptive preview; acceptance remains incomplete.
Starting application commit: `8ffe37c` on the stacked workspace branch.
No backend schema, graph builder, authentication policy or provider change.

## Implemented

- `MemoryGraphAPI.swift`: typed existing JSON contract, authenticated GET through
  JarvisHTTP, encoded focus/depth/edge-types/since, server error/truncation
  preservation, unknown node types, duplicate/dangling-node rejection and
  disclosed client limits of 500 nodes / 2,000 edges.
- `MemoryGraphLayout.swift`: deterministic, cancellable background layout,
  separated disconnected components, fixed existing points on expansion,
  camera fit/transform and existing undirected path semantics.
- `MemoryGraphStore.swift`: app-owned graph/query/selection/filter/camera state,
  bounded Back history, stale request rejection, manual-drag preservation
  during refresh, cancellation of obsolete reset work and versioned metadata
  persistence without node content. Exact fact keys can request full content
  through the existing authenticated memory overview; missing detail is stated.
- `MemoryGraphView.swift` and `MemoryGraphCanvas.swift`: direct graph access,
  graph-result integration, pan/zoom/fit/reset, node dragging, type/relationship
  filters and legend, loaded-node search, keyboard node browser, focus/depth,
  Back, node/edge inspector, path tracing, collapsed type groups, empty/error/
  partial states, explicit retry/cancel and image fallback for graph results.
  Known memory edge direction is displayed; unknown direction is not invented.
- Original graph-result payloads remain available through “Original result and
  sources”, using the unchanged shared content renderer. Non-memory graph
  images continue on the previous rendering path. Output routing is preserved.
- Layout screenshots prompted fixes for overlapping text and an empty inspector
  column. Labels now use measured non-overlapping rectangles; selected/path
  labels take priority. The inspector occupies a column only after selection.

## Automated evidence

Offline prepared Mortimer VM, sandbox task `66fed310bde6`, synthetic data only.
Commands: full `swift test --package-path macos/JarvisKit` and full
`swift test --package-path macos/MortimerHost`. No removed tests or skipped gates.

- Library: 102 tests, zero failures, check `p4-graph-library`. Log SHA-256:
  `d709f1f98e90a0a6dae4be6f346531f857bbff3754ae2e42eee41a2362b934b7`.
- Final host iteration: 62 tests, zero failures, check `p4-graph-components`.
  Log SHA-256:
  `4e5c864af90ba001de067602a94e14b6675d7f2bbc07060f6db89536c8c67c14`.
- New checks cover authenticated query encoding; disabled graphs; unknown
  types/missing provenance; node and edge caps; invalid topology; deterministic
  layout; undirected paths; stale focus replies; Back state; grouping/search;
  deleted selection; privacy of persisted metadata; manual drag versus refresh;
  camera movement versus reset; and native synthetic renderings.
- Debug-build layout times in the final host log: 50 nodes / 100 edges 0.018 s;
  200 / 400 0.239 s; 500 / 2,000 1.581 s. These are off-main layout durations,
  **not** frame times or evidence of the p95 ≤33 ms interaction gate.

## Visual evidence

Native NSHostingView snapshots, inspected by the implementing assistant. Source
fixture code is in `MemoryGraphRenderingTests.swift` / `MemoryGraphTests.swift`.
The 50-node case contains five disconnected prefix/fact/turn groups, two edge
styles, provenance and long labels. The larger cases stress dense connections.

- 50 nodes, 1,280×800 points:
  `4bd83ec855eb0c33d4b0e577f0f908df12ebbae0cfab91d37d8e108795dc05bd`.
- 200 nodes, 900×600 points:
  `5fad6ddabff620dc58b33babf2277ae297b94d892fa1d286ce12b4ee50b1cd2d`.
- 500 nodes, 1,440×900 points:
  `63a49bfa784a062d3a3475ab63bdac92307891ce2249751093a8771ac1393f98`.

PNGs are retained in the sandbox package's ignored `.build/interface-fixtures/`
directory and the host task's `work/graph-fixtures/`. This is visual layout
evidence, not proof of pointer/keyboard/VoiceOver or monitor interactions.

## Still open

- Exercise real interaction/VoiceOver, compact sheets, selected node/edge
  inspectors, path/filter/focus/back, fallback/error states and graph view
  movement between windows. Synthetic initial renderings alone do not pass P4.
- Verify p95 interaction frame time with the specified fixtures and hardware.
- Verify full detail requests, forbidden/unauthorized handling and offline
  recovery against the actual service without exposing private memory in logs.
- Authenticated fallback follow-up is implemented and covered by native tests
  below. Actual service, visual failure-state and interaction acceptance remains
  open. The separately retained original result still uses its legacy renderer.
- Complete full backend/profile/final integration gates and P0/P2/P3/P5/P6
  acceptance. This phase does not establish dual-speaker audio or monitor
  recovery, and the adaptive preview remains disabled by default.
- No merge or deployment occurred.

## Authenticated image fallback follow-up

Starting application commit `d8099ce`; isolated stacked development branch.
Direct graph access and graph-result interactive views now offer an authenticated
PNG fallback using the current graph query. The request uses the configured admin
origin and existing JarvisHTTP authorization/error mapping, never a host supplied
by an image URL. Existing default JSON requests retain their Accept header;
image requests explicitly request PNG. The response requires PNG media/signature
and a 20 MB accepted-data cap; native decoding checks the server's 3,000-pixel
per-axis limit. This is a post-download acceptance limit, not a streaming limit.

One image owner per graph retains the bitmap across view/window reconstruction,
cancels superseded work, rejects stale replies and exposes explicit reload/error
states. It does not write image data to preferences. HTTP cache/privacy review
remains part of P6; this is not evidence about URLSession disk caching. The UI
states that server images do not apply local filters or manual node placement.

Prepared offline VM, task `66fed310bde6`, full native suites:

- `p4-auth-image-library`: 103 tests, zero failures; SHA-256
  `7e77317b0c0125ddc3ac8c9949511673721602ca175443d22b667c1d9cd30387`.
- `p4-auth-image-host`: 79 tests, zero failures; SHA-256
  `1175842555f0ada00d9172e5182777c2be89d1bb7c7b4c472d4a0aa5d46e48fd`.
- New checks verify configured origin, query escaping, authorization/Accept headers,
  401/403 propagation, invalid-image rejection, retry, stale focus responses and
  reparenting without another request. These use synthetic PNG data, not a live
  memory service or private content.

Full graph interaction, frame-time, hardware and integrated acceptance remain open.

## Initial viewport fit correction

Starting application commit `087232c`. A zero/undersized initial SwiftUI viewport
or temporarily empty visible-node set previously consumed `needsFit` even though
the camera operation did nothing. Fit now waits for finite dimensions above the
camera's padding threshold and at least one visible point. The regression test
checks retained fit intent and unchanged camera for invalid/empty views, then
checks that the eventual usable fit places all fixture nodes inside the viewport.

Offline sandbox check `p4-deferred-fit-verified`: all 85 host tests pass, no skips;
SHA-256 `d67d350b8c8aee7f592aca73d1877ec6ddc9e967efbdf1e78d5f2caa11a136b6`.
The first attempt failed to compile an ambiguously typed infinity in the new
fixture; explicitly using CGFloat corrected the fixture without weakening it.
This regression check does not replace graph frame-time or hardware acceptance.

## Image cancellation recovery

Starting application commit `72ecc7b`. Cancelling an in-flight image request now
leaves a readable cancellation message with the existing explicit Reload image
action. Rebuilding the graph view does not silently retry the cancelled request;
late responses cannot replace the message, and an explicit reload can recover.

Offline sandbox check `p4-image-cancellation`: 95 host tests, zero failures,
including a new cancellation/reparent/reload regression check. Log SHA-256:
`08f54e8b9168f3086c6e32da194feb6c8aaa12adb542a84435b54720b36a3aa3`.
Full hardware and integrated acceptance remain open.

## Transient graph HTTP sessions

Starting application commit `bd9d690`. Graph JSON and fallback PNG reads now use
an ephemeral session with no URL cache, cookie storage or credential storage,
and reloadIgnoringLocalCacheData on the request. Bearer authorization, Accept
headers, timeout and status/error mapping remain in JarvisHTTP's single sender.
Production sessions are invalidated after the read. Other existing API and
signalling traffic retains its existing session behavior.

An internal AdminAPI session seam lets tests explicitly attach their URLProtocol
stub to a transient configuration. The initial test attempt showed that global
URLProtocol registration did not intercept the ephemeral session; no assertions
were removed to resolve that harness mismatch. Cache tests insert a stale
synthetic shared-cache entry, require a fresh graph response and verify that the
shared entry was not replaced. Configuration and request policy are also checked.

Offline task `66fed310bde6`, complete native suites:
- `p4-transient-session-library`: 105 tests, zero failures; SHA-256
  `ed95bfa73daf94f14aa36f8da1224c0c13184dfa030f83524d0153895ad29054`.
- `p4-transient-session-host`: 96 tests, zero failures; SHA-256
  `c763aa3d9ccf66485cdd548ce4e75cd5979f434a332b8881f59950fd11a8027e`.

This closes the identified shared URL-cache gap for the new graph JSON/PNG
requests. It does not establish comprehensive privacy, live-service, hardware,
performance or release acceptance. Legacy original-result rendering and existing
detail APIs are outside this narrowly changed request path and still need review.

## Relationship selection survives updated attributes

Refresh previously compared the entire selected relationship, including mutable
attributes. A connection whose supplied details changed therefore lost selection.
A sandbox regression test reproduced that failure before the fix:
`p4-edge-refresh-repro`, exit 1, log SHA-256
`70fbac0968891098554449f904ed071f18072f6262d88f95925469a5bf50a5a9`.

Reconciliation now prefers an exact edge match, then a unique match of directed
endpoints and relationship type, replacing the inspector data with that fresh
edge. Deleted relationships clear selection. Multiple nonmatching parallel edges
remain ambiguous and clear selection rather than inventing an identity; the API
provides no separate relationship ID. Node selection remains available.

Full sandbox host check `p4-edge-refresh-fixed`: 99 tests, zero failures; verifier
12.977 seconds. Log SHA-256:
`6f8fc25cc8132e64673c301ec80ad032b79cfb3f42a92f512ff469bfb9732932`.
Tests cover updated attributes, retained inspector state, deletion and ambiguous
parallel relationships. This is state reconciliation evidence; real graph gesture,
frame-time, accessibility and remaining integrated acceptance gates remain open.

## Retry failed full-detail reads

Graph detail errors previously occupied the full-content slot, hiding the only
load control. The store now separates detail errors from successful content and
the inspector offers Retry full detail on failure. Retry uses the existing
memoryOverview API and preserves selected node identity; it adds no automatic
request or new endpoint. Selecting another node or navigating Back clears the
old error. An unsuccessful API response remains an error, not supplied content.

Full sandbox host check `p4-detail-retry`: 100 tests, zero failures; verifier
13.375 seconds. Log SHA-256:
`528ec132920bea6e72543fc9c82a9d8c9d702bea8ec653ab34641ae5aeeb8aa0`.
A focused async test fails the first read, verifies retryable error state and
unchanged selection, then retries successfully and verifies the error clears.
The successful fixture has no matching fact and exercises the truthful missing
content message, not evidence of a live full-fact retrieval. Actual inspector
button traversal and live authenticated retrieval remain integrated checks.
