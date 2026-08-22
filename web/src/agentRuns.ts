/**
 * agentRuns — module-level store for delegated sub-agent run cards
 * (side-drawer plan §5.1 / D10 / D24).
 *
 * This state used to live inside AgentStatusPanel as component state. It
 * moved out because two components now render from it: AgentStatusPanel
 * (non-Developer runs, anchored near their satellite) and
 * AgentsTab (Developer/self-edit runs, inside the side drawer).
 * The drawer's tab body unmounts on every tab switch and whenever the
 * drawer closes (plan D23), so run state must outlive it — otherwise a
 * multi-minute self-edit's progress would be destroyed by a tab switch.
 *
 * Publish/subscribe follows the shape already established by
 * agentLayout.ts's publishFieldRect/subscribeFieldRect and wakeWord.ts's
 * subscribeWake — deliberately not React Context or a state library.
 *
 * SINGLE-LISTENER RULE (plan D10): exactly one component registers the
 * RTVI ServerMessage handler and forwards it to applyServerMessage() —
 * today that is AgentStatusPanel. Registering a second one would
 * double-apply every lifecycle event.
 */

// --- Engagement plan E5: satellite click -> Runs tab pre-filtered -------
// One-shot request slot + subscription: RunsPanel's tab body unmounts on
// every tab switch (plan D23), so a click while it's unmounted must be
// readable at its next mount (consumeRequestedAgentFilter), and a click
// while it's mounted must reach it live (subscribeAgentFilter).

type AgentFilterListener = (agent: string) => void;

let requestedAgentFilter: string | null = null;
const agentFilterListeners = new Set<AgentFilterListener>();

export function requestAgentFilter(agent: string): void {
  requestedAgentFilter = agent;
  for (const cb of agentFilterListeners) cb(agent);
}

/** Read-and-clear (one-shot) — called from RunsPanel's mount. */
export function consumeRequestedAgentFilter(): string | null {
  const value = requestedAgentFilter;
  requestedAgentFilter = null;
  return value;
}

export function subscribeAgentFilter(cb: AgentFilterListener): () => void {
  agentFilterListeners.add(cb);
  return () => {
    agentFilterListeners.delete(cb);
  };
}

export const DONE_FADE_MS = 8000;
export const MAX_TOOLS = 10;

/** ⚙ TUNING KNOB — activity ticker length per run (Larry 2026-08-21:
 * "a running text narrative related to the work being done in a
 * scrollable window"). One line per finished tool call, oldest evicted
 * past the cap. Every line is a recorded fact (the same ok verdict the
 * run log stores), never a model narrating itself. */
export const MAX_ACTIVITY = 50;

export interface ActivityLine {
  tool: string;
  ok: boolean;
  latencyMs: number;
  ts: number;
}
export const STAGES = [
  "planning",
  "proposing",
  "validating",
  "submitting",
] as const;

/** ⚙ TUNING KNOB — how many Developer runs the Agents tab keeps
 * (plan D8). Completed runs are evicted oldest-first past this cap; a run
 * still in flight is never evicted. */
export const MAX_AGENT_RUNS = 20;

export interface RunState {
  id: number;
  name: string;
  displayName: string;
  /** Backend run_id — matches the run log's identifier. "" for messages
   * from a bot that predates the field. */
  runId: string;
  task: string;
  tools: string[];
  /** Live per-tool-call ticker, bounded at MAX_ACTIVITY. */
  activity: ActivityLine[];
  stage: number; // index into STAGES (self-edit runs only)
  startedAt: number;
  doneAt: number | null;
  ok: boolean;
  detail: string;
  /** Resolved model string for this run — "" when the bot predates the
   * field. Never the configured profile name (see `model` on SubAgent). */
  model: string;
  /** A `model_profile:` was configured but could not be resolved, so
   * `model` is the voice-model fallback rather than the assignment. */
  modelFallback: boolean;
  /** K4 — the model resolved fine, but its credential was actively refused
   * or could not be billed, so every call through it will fail. Distinct
   * from modelFallback: nothing upstream noticed anything wrong. */
  modelUnusable: boolean;
  modelUnusableDetail: string;
  /** G7 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
   * model actually doing self-edit WORK inside the admin sidecar — distinct
   * from `model` above (the developer SubAgent's own resolved model, e.g.
   * Haiku or kimi-k3, which merely dispatched selfedit_start). "" until a
   * selfedit_start/selfedit_status result has reported it. */
  plannerModel: string;
}

interface AgentLifecycleMsg {
  type?: string;
  name?: string;
  display_name?: string;
  state?: string;
  run_id?: string;
  task?: string;
  ok?: boolean;
  detail?: string;
  tool?: string;
  latency_ms?: number;
  model?: string;
  model_fallback?: boolean;
  model_unusable?: boolean;
  model_unusable_detail?: string;
  planner_model?: string;
}

/**
 * Shorten a model string for the card header, keeping the part that
 * identifies it. `moonshotai/kimi-k2.5-instruct` -> `kimi-k2.5-instruct`;
 * anything still long is truncated. The FULL string goes in the element's
 * title attribute, so shortening never destroys information — it only
 * decides what fits.
 */
export function shortModel(model: string, max = 22): string {
  const tail = model.trim().split("/").pop() ?? "";
  return tail.length > max ? tail.slice(0, max - 1) + "…" : tail;
}

export function clamp(s: string, max: number): string {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

export function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}:${String(s % 60).padStart(2, "0")}` : `${s}s`;
}

/** Map a tool name onto a self-edit stage. */
export function toolStage(tool: string): number {
  const t = tool.toLowerCase();
  if (/valid|test|pytest|check/.test(t)) return 2;
  if (/submit|push|pull_request|\bpr\b/.test(t)) return 3;
  if (/propos|write|edit|apply|patch|create/.test(t)) return 1;
  return 0;
}

/**
 * Development runs (developer agent / selfedit_* tools) get stages, and —
 * since the side drawer — render in the Agents tab instead of as an
 * anchored satellite card.
 *
 * Plan D9 states plainly what this currently means: `name` is the agent
 * key, so `"developer".includes("develop")` is true for EVERY developer
 * run, before any tool is called. This function does not discriminate
 * between self-edit work and ordinary developer work, and the plan accepts
 * that: the Developer satellite at the pentagon apex will never show an
 * anchored card.
 */
export function isSelfEditRun(name: string, tools: string[]): boolean {
  const n = name.toLowerCase();
  return (
    n.includes("self") ||
    n.includes("edit") ||
    n.includes("develop") ||
    tools.some((t) => t.toLowerCase().startsWith("selfedit"))
  );
}

// --- store ---------------------------------------------------------------

let runs: RunState[] = [];
export type RunsListener = (runs: RunState[]) => void;
const listeners = new Set<RunsListener>();

let seq = 0;
const runIds = new Map<string, number>(); // agent name -> LIVE run id
const timers = new Map<number, ReturnType<typeof setTimeout>>();

/** Current runs, oldest first. Treat the returned array as immutable. */
export function getRuns(): RunState[] {
  return runs;
}

/** Subscribe to run changes; returns an unsubscribe function — same
 * contract as agentLayout.ts's subscribeFieldRect. Listeners fire
 * synchronously after each mutation, with the new array. */
export function subscribeRuns(cb: RunsListener): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function setRuns(next: RunState[]): void {
  runs = next;
  for (const cb of listeners) cb(runs);
}

/**
 * MORTIMER_DRAWER_POPOUT_PLAN.md DP3 — the drawer window's copy of this
 * store has no RTVI connection (D10's single-listener rule lives in
 * AgentStatusPanel, console-only) and is instead fed by the console
 * relaying every applyServerMessage-driven change onto the drawer's
 * BroadcastChannel (web/src/drawerRelay.ts). This setter is that relay's
 * ONLY mutator on the popped side: it replaces the array wholesale rather
 * than replaying insertRun/timer bookkeeping, which is console-only
 * concern (fade-out timers only matter for the anchored satellite cards
 * that never render in the drawer window).
 */
export function applyRelayedRuns(next: RunState[]): void {
  setRuns(next);
}

function clearTimer(id: number): void {
  const t = timers.get(id);
  if (t !== undefined) {
    clearTimeout(t);
    timers.delete(id);
  }
}

export function removeRun(id: number): void {
  const run = runs.find((r) => r.id === id);
  if (run && runIds.get(run.name) === id) runIds.delete(run.name);
  clearTimer(id);
  setRuns(runs.filter((r) => r.id !== id));
}

/**
 * Plan D8a — the per-agent replacement rule, narrowed.
 *
 * Non-Developer runs keep the original behavior: a new run for an agent
 * replaces that agent's previous card. Developer runs APPEND instead, so
 * the Agents tab accumulates history (D8); when the agent's list
 * exceeds MAX_AGENT_RUNS the OLDEST COMPLETED run is dropped. A run
 * still in flight is never dropped, even if it is the oldest.
 */
function insertRun(list: RunState[], run: RunState): RunState[] {
  if (!isSelfEditRun(run.name, run.tools)) {
    return [...list.filter((r) => r.name !== run.name), run];
  }
  let next = [...list, run];
  while (next.filter((r) => r.name === run.name).length > MAX_AGENT_RUNS) {
    const victim = next.find((r) => r.name === run.name && r.doneAt !== null);
    if (victim === undefined) break; // all in flight — never evict a live run
    clearTimer(victim.id);
    next = next.filter((r) => r.id !== victim.id);
  }
  return next;
}

/**
 * Apply one RTVI server message. Type-guards internally; a message of
 * unrecognized shape is ignored. This is the ONLY function that mutates
 * run state from RTVI events.
 */
export function applyServerMessage(msg: unknown): void {
  const m = msg as AgentLifecycleMsg;
  if (typeof m?.type !== "string" || typeof m?.name !== "string") return;
  const name = m.name;
  const displayName =
    typeof m.display_name === "string" && m.display_name !== ""
      ? m.display_name
      : name;

  if (m.type === "agent" && m.state === "working") {
    const prevId = runIds.get(name);
    if (prevId !== undefined) clearTimer(prevId);
    seq += 1;
    const id = seq;
    runIds.set(name, id);
    const run: RunState = {
      id,
      name,
      displayName,
      runId: typeof m.run_id === "string" ? m.run_id : "",
      task: typeof m.task === "string" ? clamp(m.task, 200) : "",
      tools: [],
      activity: [],
      stage: 0,
      startedAt: Date.now(),
      doneAt: null,
      ok: false,
      detail: "",
      model: typeof m.model === "string" ? m.model : "",
      modelFallback: m.model_fallback === true,
      modelUnusable: m.model_unusable === true,
      modelUnusableDetail:
        typeof m.model_unusable_detail === "string" ? m.model_unusable_detail : "",
      plannerModel: "",
    };
    setRuns(insertRun(runs, run));
  } else if (m.type === "agent_activity" && typeof m.tool === "string") {
    // One line per FINISHED tool call. Matched by backend run_id when
    // both sides carry one (precise even with parallel same-agent runs),
    // else by the agent's live run — the same fallback agent_tool uses.
    const runId = typeof m.run_id === "string" ? m.run_id : "";
    const line: ActivityLine = {
      tool: m.tool,
      ok: m.ok !== false,
      latencyMs: typeof m.latency_ms === "number" ? m.latency_ms : 0,
      ts: Date.now(),
    };
    // G7 — selfedit_start/selfedit_status results ride planner_model on
    // this SAME per-tool-call message; once seen it sticks on the card
    // (never cleared back to "" by a later tool call that didn't report
    // one — a card that HAD a planner model never silently loses the chip).
    const plannerModel =
      typeof m.planner_model === "string" && m.planner_model !== ""
        ? m.planner_model
        : undefined;
    setRuns(
      runs.map((r) => {
        const match =
          runId !== "" && r.runId !== ""
            ? r.runId === runId
            : r.name === name && r.doneAt === null;
        return match
          ? {
              ...r,
              activity: [...r.activity, line].slice(-MAX_ACTIVITY),
              plannerModel: plannerModel ?? r.plannerModel,
            }
          : r;
      }),
    );
  } else if (m.type === "agent_tool" && typeof m.tool === "string") {
    const tool = m.tool;
    setRuns(
      runs.map((r) =>
        r.name === name && r.doneAt === null
          ? {
              ...r,
              displayName,
              tools: [...r.tools, tool].slice(-MAX_TOOLS),
              stage: Math.max(r.stage, toolStage(tool)),
            }
          : r,
      ),
    );
  } else if (m.type === "agent" && m.state === "done") {
    // Bots predating ok/detail send neither — assume success.
    const ok = m.ok !== false;
    const detail = typeof m.detail === "string" ? clamp(m.detail, 300) : "";
    setRuns(
      runs.map((r) =>
        r.name === name && r.doneAt === null
          ? { ...r, displayName, doneAt: Date.now(), ok, detail }
          : r,
      ),
    );
    // runIds keeps pointing at this run until it is removed — that is what
    // lets the next "working" message for the same agent cancel a pending
    // fade timer (clearTimer(prevId) above).
    const id = runIds.get(name);
    const settled = id === undefined ? undefined : runs.find((r) => r.id === id);
    // Plan D8: Developer runs are exempt from the 8s success fade — the
    // drawer tab is a surface the user deliberately opened to read, so it
    // keeps a bounded history instead of emptying itself.
    if (
      ok &&
      id !== undefined &&
      settled !== undefined &&
      !isSelfEditRun(settled.name, settled.tools)
    ) {
      clearTimer(id);
      timers.set(
        id,
        setTimeout(() => removeRun(id), DONE_FADE_MS),
      );
    }
  }
}
