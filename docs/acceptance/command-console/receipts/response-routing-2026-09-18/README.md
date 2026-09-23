# Mortimer answers in results — September 18, 2026

User decision: full answers belong in the existing response/results area,
owned by the supporting display when open, with brief live conversation captions.

## Implemented behavior

- Layout 2 routes existing transcript updates through the app-scoped message
  router into one in-memory result per user request. Assistant subturns around
  tools append to that same result. No added model calls or persistence.
- Streamed text updates stable workspace and supporting-tile identities.
  Pins, inspector and scroll state remain intact. Closing a result or tile
  prevents later chunks from reopening it. Separate requests remain distinct
  even when their answer text is identical.
- Startup stays in compact Conversation until an answer arrives. Replies
  replace Conversation or the preceding unpinned response; explicit Atlas,
  graph, comparison or unrelated research selection is preserved.
- The supporting window owns full text while open, with a main-window return
  locator. Closing it reveals the same answer in main results. The existing
  four-tile stage budget applies; older replies remain in result history.
- Conversation captions show the latest 160 characters; full transcript Log,
  copy/share/export, voice controls and legacy layouts remain available.
- New result identities publish the voice-control inventory. Body-only chunks
  do not invalidate pending voice commands or flood inventory publication.

## Evidence and limits

`targeted-tests.log` records 38 passing tests across response routing,
workspace state and content panels. `render-tests.log` records four passing
supporting-display tests, including real native windows on both connected
screens. Synthetic streamed text is visible only on the supporting surface,
then appears in the main result reader after supporting-window close. The
three `response-*.png` captures document those rendered states.

These are native rendering tests with synthetic replies, not a live model
conversation. A later live candidate check reached `READY VOICE` after
reconnect and verified the same ownership path with existing session data: the
main console showed `Memory graph is on the supporting display` and `Return
here`, while the supporting window showed one bounded stage containing the
memory graph and Mortimer response card. This is live native-window evidence,
but not a new spoken model request, so active two-channel audio and provider
response acceptance remain open.

Closing the supporting window then left the candidate at `READY VOICE` with
the response selected and the memory graph rendered in the main surface. No
additional window was created during the return.

Physical unplug/reconnect, mirrored and three-screen scenarios, live
spoken-response evidence and final candidate acceptance remain open. The
separately diagnosed CoreAudio startup issue is not claimed resolved.
UI2-06/UI2-19/UI2-20 remain unchecked; the atom-style visualization remains queued.

Full regression: MortimerHost **241 passed**, JarvisKit **190 passed**, zero
failures (`host-full.log`, `kit-full.log`). P4 graph p95 is **9.908 ms** over
300 frames, below the unchanged 33 ms gate (`P4-frame-time.json`).

## Built and running candidate

The debug bundle was rebuilt and signature-verified. Executable SHA-256:
`81cdfb0efeabfec9b9c83a3e4661f04fa708d82303ff6be2d5df0463faaea4aa`.
The exact release-review app launched as PID 82363 and opened in compact
Conversation. Native accessibility inspection then verified READY VOICE and
loaded the graph (405 visible / 500 loaded nodes; 37 relationships). The earlier
CoreAudio startup timeout did not recur on this launch; this single success
does not establish that the underlying intermittent condition is fixed.

No live spoken response was observed during this check. Subsequent computer-use
operations took 76–95 seconds and returned stale element errors while trying
to restore the graph to the supporting window. That final live handoff is not
counted as passed. The passing two-screen rendering tests above remain the
evidence for response ownership and return-to-main behavior.
