# Implementation Plan: Interval-Based Polling Capability

## 1. Problem Statement

The project has no reusable mechanism for repeatedly executing an asynchronous operation on a fixed time interval. Callers that need to poll (e.g., re-fetch a status endpoint, refresh a resource) must hand-roll `setInterval` logic, which typically gets three things wrong: overlapping executions when the operation outlives the interval, unhandled promise rejections from failed polls, and no clean shutdown. This plan adds a single, well-tested polling primitive that handles scheduling, overlap prevention, error routing, and cancellation.

## 2. Assumptions (Ambiguities That Could Not Be Resolved From the Goal)

The goal names no codebase, language, or runtime. The following assumptions were made so the plan can be fully concrete; each is stated here rather than left open:

- **Language/runtime:** TypeScript, targeting both Node.js (≥18) and browsers. No runtime dependencies.
- **Test runner:** Vitest (its fake-timer API is used in the verification steps).
- **Project layout:** a `src/` directory with a package entry point at `src/index.ts` and tests under `tests/`.
- **Scope:** this is a library-level utility, not wired into any specific feature. If the goal intended polling for one specific call site (e.g., "poll endpoint X"), this plan still delivers the correct primitive; wiring it to that call site is out of scope.

If the actual repository differs (JavaScript instead of TypeScript, Jest instead of Vitest), the mechanical adaptations are: drop type annotations, and substitute `jest.useFakeTimers()` / `jest.advanceTimersByTimeAsync()` for the Vitest equivalents. No design decisions change.

## 3. Decisions

### 3.1 Scheduling strategy: fixed-delay, never fixed-rate

Use a **recursive `setTimeout` chain**, where the next tick is scheduled only after the previous poll's promise settles. Explicitly do **not** use `setInterval`. Consequences, chosen deliberately:

- Overlapping executions are impossible by construction.
- Effective period = poll duration + `intervalMs` (interval is measured *between* polls, not start-to-start). This is documented in the API docs as intended behavior.

### 3.2 Public API

One class, exported from `src/polling/poller.ts`:

- **`new Poller<T>(options)`** — constructs but does not start.
- **`start(): void`** — idempotent; calling while already running is a no-op. If `immediate` is true (default), the first poll fires synchronously on `start()`; otherwise the first poll fires after one full interval. On every `start()`, a fresh internal `AbortController` is created so the poller is restartable after `stop()`.
- **`stop(): void`** — cancels the pending timer (if any) and aborts the internal `AbortController`. An in-flight poll is allowed to complete, and its result/error **is** still delivered to callbacks, but no further polls are scheduled. Idempotent.
- **`pollNow(): Promise<void>`** — triggers a poll immediately, outside the schedule. If a poll is currently in flight, it is a **no-op** (returns a resolved promise) rather than stacking a concurrent execution.
- **`status: 'idle' | 'running'`** — read-only getter.

Options object (all decisions final):

| Option | Type | Default | Behavior |
|---|---|---|---|
| `fn` | `(ctx: PollContext) => T \| Promise<T>` | required | The operation to poll. May be sync or async; always awaited. |
| `intervalMs` | `number` | required | Delay between the end of one poll and the start of the next. |
| `immediate` | `boolean` | `true` | Whether `start()` polls immediately or after one interval. |
| `stopOnError` | `boolean` | `false` | If true, a rejected poll stops the poller; if false, polling continues. |
| `signal` | `AbortSignal` | none | External signal; aborting it calls `stop()`. Listener is removed on `stop()`. |
| `onResult` | `(value: T) => void` | none | Called with each successful result. |
| `onError` | `(error: unknown) => void` | `console.error` | Called with each failure. |

`PollContext` passed to `fn` on every invocation:

- `signal: AbortSignal` — the internal controller's signal; aborted on `stop()` so `fn` can cancel in-flight work (e.g., pass to `fetch`).
- `pollNumber: number` — 1-based count of poll attempts since the most recent `start()`.

### 3.3 Validation (at construction, fail fast)

- `fn` not a function → throw `TypeError`.
- `intervalMs` not a finite number or `< 1` → throw `RangeError`.

### 3.4 Internal state and control flow

- Mutable private fields: timer handle (typed `ReturnType<typeof setTimeout>` for Node/browser compatibility), `inFlight: boolean`, `status`, internal `AbortController | null`, attempt counter.
- The scheduler loop: clear timer → check running → set `inFlight` → increment counter → invoke `fn` in `try/catch` and `await` → route result to `onResult` or error to `onError` → clear `inFlight` → if still running (and not stopped by `stopOnError`), schedule next `setTimeout(tick, intervalMs)`.
- Exceptions thrown **by the user's `onError` or `onResult` callbacks** are caught and routed to `console.error`; they never break the scheduling loop or cause unhandled rejections.
- All poll invocations are wrapped so a rejected `fn` promise never produces an unhandled rejection regardless of whether callbacks are attached.
- The poller does **not** cache the last result or error; it is stateless apart from status and counters, avoiding unbounded memory retention of polled payloads.
- External `signal` handling: register one `abort` listener on `start()` (if provided), remove it on `stop()`.

### 3.5 Export surface

- `src/polling/poller.ts` exports `Poller`, `PollerOptions`, `PollContext` (types and class in one file — no separate types file).
- `src/polling/index.ts` re-exports all three.
- `src/index.ts` (package entry) re-exports from `./polling/index.js` so the capability is public API.

## 4. Files

| File | Action | Contents |
|---|---|---|
| `src/polling/poller.ts` | Create | Types (`PollerOptions`, `PollContext`) and `Poller` class per §3.2–3.4 |
| `src/polling/index.ts` | Create | Barrel re-export |
| `src/index.ts` | Modify | Add re-export of the polling module |
| `tests/polling/poller.test.ts` | Create | Full test suite per §6 |

No configuration changes, no new dependencies.

## 5. Implementation Order

1. Create `src/polling/poller.ts`: define `PollContext` and `PollerOptions` types first, then the `Poller` class — constructor with validation (§3.3), then `start()`, `stop()`, `pollNow()`, the private tick/scheduler method, and the `status` getter.
2. Create `src/polling/index.ts` barrel.
3. Modify `src/index.ts` to re-export the polling module.
4. Create `tests/polling/poller.test.ts` with the suite in §6.
5. Run the verification steps in §6; fix only defects, do not redesign.

## 6. Verification

### 6.1 Automated tests (`tests/polling/poller.test.ts`)

Use `vi.useFakeTimers()` and a small deferred-promise helper so each test fully controls when `fn` resolves. Required cases, each as its own test:

1. Constructor throws `TypeError` for non-function `fn`; throws `RangeError` for `intervalMs` of `0`, negative, `NaN`, `Infinity`.
2. With `immediate: true` (default), `fn` is called exactly once synchronously after `start()`, before any timer advance.
3. With `immediate: false`, `fn` is not called until `intervalMs` elapses.
4. Polls repeat: advancing time by `3 × intervalMs` (with instantly-resolving `fn`) yields the expected total call count.
5. **No overlap:** `fn` returns a promise that is resolved manually *after* advancing the clock past `intervalMs`; assert only one call occurred and the next call happens `intervalMs` after resolution (use `vi.advanceTimersByTimeAsync`).
6. `stop()` prevents all future polls; call count frozen across further timer advances.
7. In-flight poll completes after `stop()`: its result is still delivered to `onResult`, but no rescheduling occurs.
8. Rejected `fn` with defaults: `onError` receives the error, polling continues on schedule.
9. Rejected `fn` with `stopOnError: true`: poller stops, `status` becomes `'idle'`, no further calls.
10. `pollNow()` triggers an immediate extra poll; `pollNow()` during an in-flight poll is a no-op (call count unchanged).
11. External `AbortSignal`: aborting stops polling; subsequent `start()` works (restartability) and the new `ctx.signal` is not the aborted one.
12. `ctx.pollNumber` increments 1, 2, 3… across polls within one `start()`.
13. An `onError` callback that itself throws does not stop the scheduler loop.
14. No unhandled rejections: attach a process-level `unhandledRejection` listener during the error tests and assert it never fires.

### 6.2 Commands

- `npx vitest run` — all tests pass.
- `npx tsc --noEmit` — clean typecheck.
- Lint per repo config (e.g., `npx eslint src/polling tests/polling`) — clean.

### 6.3 Manual smoke check

A throwaway Node script (not committed): construct a `Poller` over an incrementing counter with `intervalMs: 100`, run for ~1 second, `stop()`, and print the call count and elapsed time. Expected: 9–11 calls, monotonically increasing `pollNumber`, and no further calls after `stop()` (verify by waiting an additional 300 ms and re-checking the count).

## 7. Risks

- **Overlapping executions** (the classic polling bug): eliminated by design via the fixed-delay recursive-`setTimeout` strategy plus the `inFlight` guard; test 5 is the regression guard.
- **Unhandled promise rejections** from failed polls crashing Node processes: all invocations are wrapped and errors routed to `onError`; test 14 verifies.
- **Fake-timer/async interleaving producing flaky tests**: mitigated by the deferred-promise helper and `advanceTimersByTimeAsync` rather than mixing real and fake time.
- **Timer drift / period longer than `intervalMs`**: inherent to the fixed-delay choice; it is documented as intended. Callers needing fixed-rate semantics are out of scope (§8).
- **Cross-platform timer typing** (`NodeJS.Timeout` vs `number`): handled by `ReturnType<typeof setTimeout>`; the `tsc --noEmit` step verifies.
- **Listener leak on external `AbortSignal` across repeated start/stop cycles**: the abort listener is removed in `stop()`; test 11 exercises restart.
- **Scope ambiguity** (unknown target codebase): surfaced explicitly in §2 rather than hidden; the design has no repo-specific coupling, so misplaced file paths are the only cost of a wrong assumption.

## 8. What This Plan Deliberately Does NOT Do

- **No retry/backoff/jitter strategies** — fixed interval only; exponential backoff would need failure-classification policy the goal does not specify.
- **No stop-condition predicates** (`until: (result) => boolean`) or maximum-attempt caps.
- **No fixed-rate scheduling** (start-to-start intervals); fixed-delay is the chosen and documented semantic.
- **No Page Visibility / network-status integration** (pausing when tab is hidden or offline).
- **No wiring into any specific feature or endpoint** — this delivers the primitive only (see §2).
- **No result caching or change detection** (emitting only when the polled value changes).

---
*Drafted by kimi-k3 (kimi-k3) — 2026-08-30.*