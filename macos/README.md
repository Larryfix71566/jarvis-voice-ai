# macos/

- **`JarvisKit/`** — the shared client package (this plan,
  `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`). The single implementation of the
  voice session, the admin sidecar API, and the wake-word path.
- **`GlassSpike/`** — a throwaway T1.1 target. Delete it after G1(a)
  (Larry signs `GlassSpike/README.md`).
- **`MortimerHost/`** — the G1(b) debug harness that T1.3 grows into the
  real native app.
- **`MortimerShell/`** — the outgoing WKWebView shell. Deleted by T1.4,
  gated on G1(e) (five consecutive daily-driver days). Not touched by
  this plan.

`macos/**` is on the self-edit deny list
(`config/self_edit_allowlist.json`) — none of this work is ever eligible
for the self-edit path; it is a human PR (§0.2, C8).
