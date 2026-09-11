# Synthetic graph desktop fixture

`GraphFixtureServer.py` provides bounded synthetic data for manual interaction
checks in the disposable offline GUI VM. It is not the production admin service
and cannot establish authenticated backend integration acceptance.

Run it only as the VM worker (UID 502). The executable entry point verifies that
it is inside a hypervisor and binds only `127.0.0.1:7861`; an occupied port is an
error. It uses neither the project vault nor real memory. Record and stop the
specific process started for the check after finishing. Launch background helpers
with stdin detached and stdout/stderr redirected to a worker-owned log; use
bounded health requests shorter than the sandbox command timeout.

The normal response contains five synthetic project groups, 50 nodes and 80
relationships. Focus on `prefix:project.0` at depth 2 returns 10 nodes and 16
relationships. Unknown focus returns an empty result. Node labels and provenance
explicitly identify fixture content. GET health and graph routes are implemented;
other GET routes return 404 and POST/PUT/PATCH/DELETE return 405.

In `/Users/mortimer-dev/graph-acceptance/mode.json`, a JSON object with a `mode`
field selects `normal`, `error` (503), `invalid` (unsupported graph schema), or
`empty`. Write this test input before using the app's Refresh or Retry controls.
Requests are logged by path and mode, without headers. Full-memory detail and
image fallback responses are intentionally absent; success for those operations
requires a different fixture or the real service.

The server bypasses HTTPServer's reverse-DNS lookup for its fixed loopback
identity. An earlier startup helper exceeded its command timeout and the sandbox
controller stopped that VM. The working helper uses this DNS-independent bind,
bounded health polling and cleanup of only its own process on startup failure.
