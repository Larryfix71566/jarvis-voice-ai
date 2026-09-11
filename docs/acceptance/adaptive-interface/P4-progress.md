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
- Extend/verify authenticated image fallback for direct graph access (which
  has no originating image URL). Existing graph-result fallback currently uses
  the preserved image renderer; it has not passed authenticated fallback testing.
- Complete full backend/profile/final integration gates and P0/P2/P3/P5/P6
  acceptance. This phase does not establish dual-speaker audio or monitor
  recovery, and the adaptive preview remains disabled by default.
- No merge or deployment occurred.
