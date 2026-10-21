# Claude2.1.291 — offline native protocol compatibility

Actual installed2.1.291 binary with `claude-haiku-4-5` passed positive and hostile
localhost protocol rounds using the existing native-session implementation and
two synthetic stub schemas (`repo_read_file`, `selfedit_finish`). No real file
read/edit callback or model inference occurs. The positive case preserves
initialization, schema advertisements, tool/result continuation and PostToolUse
constraints. The hostile case refuses an unadvertised Bash request before any
host callback; its side-effect canary remains absent. Unknown gateway tools,
customization isolation, synthetic authentication and owned cleanup pass.

The [JSON](ws17-claude-291-native-contract-2026-10-21.json) records binary/protocol,
source/artifact and local receipt hashes without installed paths or account data.
The [replayable fixture](ws17-claude-291-offline-probe.py) inspects only an already
installed executable, uses fake HOME/auth and local endpoints, and never changes
a gate or creates workload acceptance. Redirect replay output to a private local
receipt. Production version admission remained unchanged during acquisition.

The source compatibility change adds only exact2.1.291 alongside2.1.290; unknown
versions still refuse. Every tools-enable flag and exact request/model/schema/
executable capability receipt, privacy/source floor and activation gate remains.
This artifact is deliberately not a workload capability receipt and cannot
substitute for one. No live authentication, quality, latency, interruption,
streaming, real voice or private-context acceptance is inferred. Independent
source review and final-head CI for the compatibility change remain required.

Regression: the new exact2.1.291 compatibility case was refused before the source
change (one failure/three controls); after the change330 directly affected tests
pass/one dependency warning/11.26s. Unknown and preview variants refuse, typed
receipt checks cover both versions, and an offline probe artifact cannot enable
a native workload. This is source compatibility, not activation or live proof.
