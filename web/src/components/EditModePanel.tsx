import { useCallback, useEffect, useRef, useState } from "react";

const API = "http://localhost:7861";

interface Proposal {
  path: string;
  rationale: string;
  diff: string;
}

interface SessionStatus {
  active: boolean;
  branch: string | null;
  rollback_tag: string | null;
  goal: string | null;
  proposals: Proposal[];
  validated_ok: boolean;
}

interface ModelProfile {
  name: string;
  label: string;
  provider: string;
  model: string;
  key_env: string;
  key_present: boolean;
  default: boolean;
  tier: TierName | null;
}

interface RunJob {
  state: "idle" | "running" | "done" | "error";
  goal?: string | null;
  profile?: string | null;
  summary?: string | null;
}

interface Check {
  name: string;
  ok: boolean;
  output: string;
}

const MERGE_NOTE =
  "Review and merge on GitHub — Jarvis cannot merge this.";

// --- LLM Council (MORTIMER_LLM_COUNCIL_PLAN.md D9/D10) ------------------
//
// Membership selection is UI-only state, kept separate from the model
// registry (config/upgrade_models.yaml stays off the self-edit allowlist —
// D9's whole reason for this split). Same localStorage discipline as the
// drawer's own `mortimer.drawer.*` keys (App.tsx): every read is wrapped
// in try/catch and validated, never trusted as-is.

type TierName = "economy" | "mid" | "frontier";
const TIER_NAMES: TierName[] = ["economy", "mid", "frontier"];

interface CouncilWinner {
  profile: string;
  content: string;
}

interface ConveneResult {
  ok: boolean;
  round_id?: string;
  winner?: CouncilWinner | null;
  winner_mean?: number | null;
  select_reason?: string;
  error?: string;
}

// MORTIMER_LLM_COUNCIL_V2_PLAN.md V5 — the shape of _council_job, polled
// via GET /api/council/job (same idle/running/done/error shape as
// RunJob's own job-polling pattern above).
interface CouncilJob {
  state: "idle" | "running" | "done" | "error";
  trigger?: "manual" | "E3" | null;
  goal?: string | null;
  round_id?: string | null;
  winner?: CouncilWinner | null;
  winner_mean?: number | null;
  select_reason?: string | null;
  error?: string | null;
}

// V12 — one row of GET /api/council/rounds; a loose subset of the
// council_rounds columns (jarvis/db.py MIGRATION_0009), only what the
// "Recent rounds" list renders.
interface CouncilRoundSummary {
  round_id: string;
  started_at: string;
  trigger: string;
  tier: number;
  status: string;
  winner_profile: string | null;
  retry_validated: number | null;
}

interface CouncilScoreRow {
  judge_profile: string;
  judge_tier: string;
  shadow: number;
  proposal_label: string;
  proposal_profile: string;
  score: number | null;
  abstain_reason: string | null;
  justification: string | null;
}

interface CouncilRoundDetail {
  ok: boolean;
  round?: { round_id: string; goal: string; winner_label: string | null };
  scores?: CouncilScoreRow[];
}

// --- Planning pathway (MORTIMER_PLANNING_PATHWAY_PLAN.md P7) ------------

interface PlanCandidate {
  label: string;
  profile: string;
  content: string;
  advisory_mean: number | null;
}

interface PlanJob {
  state: "idle" | "running" | "awaiting_choice" | "done" | "error";
  mode?: "single" | "council" | null;
  goal?: string | null;
  profile?: string | null;
  round_id?: string | null;
  candidates?: PlanCandidate[] | null;
  plan?: string | null;
  author?: string | null;
  error?: string | null;
  // MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R1 — set (repo-relative path)
  // when this job is a review of an existing document rather than a
  // fresh plan/spec authoring job.
  review_path?: string | null;
}

const IDLE_PLAN_JOB: PlanJob = { state: "idle" };

function lsKeyForTier(tier: TierName): string {
  return `mortimer.council.${tier}`;
}

function readStoredTierSelection(tier: TierName): string[] {
  try {
    const raw = localStorage.getItem(lsKeyForTier(tier));
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string");
  } catch {
    return [];
  }
}

function writeStoredTierSelection(tier: TierName, names: string[]): void {
  try {
    localStorage.setItem(lsKeyForTier(tier), JSON.stringify(names));
  } catch {
    /* storage unavailable (private browsing, quota) — selection just
       won't persist across reloads; convening still works this session */
  }
}

export default function EditModePanel() {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [profile, setProfile] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- council state ---
  const [councilSelection, setCouncilSelection] = useState<
    Record<TierName, string[]>
  >(() => ({
    economy: readStoredTierSelection("economy"),
    mid: readStoredTierSelection("mid"),
    frontier: readStoredTierSelection("frontier"),
  }));
  const [councilGoal, setCouncilGoal] = useState("");
  const [councilBusy, setCouncilBusy] = useState(false);
  const [councilNote, setCouncilNote] = useState<string | null>(null);
  const [councilResult, setCouncilResult] = useState<ConveneResult | null>(null);
  const [councilRound, setCouncilRound] = useState<CouncilRoundDetail | null>(null);
  const councilPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [councilRoundsOpen, setCouncilRoundsOpen] = useState(false);
  const [councilRounds, setCouncilRounds] = useState<CouncilRoundSummary[] | null>(null);

  // --- planning pathway state (P7) ---
  const [planGoal, setPlanGoal] = useState("");
  const [planMode, setPlanMode] = useState<"single" | "council">("single");
  const [planProfile, setPlanProfile] = useState("");
  const [planJob, setPlanJob] = useState<PlanJob>(IDLE_PLAN_JOB);
  const [planNote, setPlanNote] = useState<string | null>(null);
  const [planAdoptPath, setPlanAdoptPath] = useState("");
  const [planReviewPath, setPlanReviewPath] = useState("");
  const planPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/selfedit/status`);
      setStatus(await r.json());
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/selfedit/models`);
      const j = (await r.json()) as { ok: boolean; models: ModelProfile[] };
      if (j.ok) {
        setModels(j.models);
        const dflt =
          j.models.find((m) => m.default && m.key_present) ??
          j.models.find((m) => m.key_present);
        if (dflt) setProfile(dflt.name);
      }
    } catch {
      /* offline state is surfaced by refresh() */
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/selfedit/run`);
        const j = (await r.json()) as { ok: boolean; job: RunJob };
        if (!j.ok) return;
        if (j.job.state !== "running") {
          stopPolling();
          setSummary(j.job.summary ?? null);
          setBusy(null);
          void refresh();
        }
      } catch {
        stopPolling();
        setBusy(null);
      }
    }, 3000);
  }, [refresh, stopPolling]);

  const stopCouncilPolling = useCallback(() => {
    if (councilPollRef.current) {
      clearInterval(councilPollRef.current);
      councilPollRef.current = null;
    }
  }, []);

  const stopPlanPolling = useCallback(() => {
    if (planPollRef.current) {
      clearInterval(planPollRef.current);
      planPollRef.current = null;
    }
  }, []);

  useEffect(() => {
    void refresh();
    void loadModels();
    return () => {
      stopPolling();
      stopCouncilPolling();
      stopPlanPolling();
    };
  }, [refresh, loadModels, stopPolling, stopCouncilPolling, stopPlanPolling]);

  const post = async (path: string, body?: object) => {
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.json();
  };

  const onRun = async () => {
    setBusy("run");
    setNote(null);
    setPrUrl(null);
    try {
      const res = await post("/api/selfedit/run", {
        goal,
        profile: profile || undefined,
      });
      if (res.ok && res.started) {
        setNote(`planning with ${res.profile} — this can take several minutes…`);
        startPolling(); // busy stays "run" until the job settles
      } else {
        setNote(res.error ?? "could not start the run");
        setBusy(null);
      }
    } catch {
      setNote("agent run failed — is the admin sidecar running?");
      setBusy(null);
    }
  };

  const onValidate = async () => {
    setBusy("validate");
    setNote(null);
    const res = await post("/api/selfedit/validate");
    setChecks(res.checks ?? null);
    setNote(res.ok ? "validation passed" : res.error ?? "validation failed");
    void refresh();
    setBusy(null);
  };

  const onSubmit = async () => {
    setBusy("submit");
    setNote(null);
    const res = await post("/api/selfedit/submit");
    if (res.ok) {
      setPrUrl(res.pr_url);
      setChecks(null);
      setSummary(null);
      setGoal("");
    } else {
      setNote(res.error ?? "submit failed");
    }
    void refresh();
    setBusy(null);
  };

  const onRevert = async () => {
    setBusy("revert");
    setNote(null);
    const res = await post("/api/selfedit/revert");
    setNote(res.ok ? `session reverted to ${res.reverted_to}` : res.error);
    setChecks(null);
    setSummary(null);
    void refresh();
    setBusy(null);
  };

  // --- council -----------------------------------------------------------

  const modelsByTier = (tier: TierName) => models.filter((m) => m.tier === tier);

  const toggleCouncilMember = (tier: TierName, name: string) => {
    setCouncilSelection((prev) => {
      const current = prev[tier];
      const next = current.includes(name)
        ? current.filter((n) => n !== name)
        : [...current, name];
      writeStoredTierSelection(tier, next);
      return { ...prev, [tier]: next };
    });
  };

  // D9: "minimum 2 selectable members enforced in the UI." An empty
  // selection means "use the full tier" (always valid — D9's fallback
  // rule), so this only blocks a PARTIAL selection of exactly one, which
  // is the one state that would silently shrink a council below the
  // floor without the empty-selection fallback to save it.
  const tierSelectionInvalid = (tier: TierName) =>
    councilSelection[tier].length === 1;
  const anyCouncilSelectionInvalid = TIER_NAMES.some(tierSelectionInvalid);

  const loadCouncilRound = async (roundId: string) => {
    try {
      const r = await fetch(`${API}/api/council/round/${roundId}`);
      const j = (await r.json()) as CouncilRoundDetail;
      setCouncilRound(j.ok ? j : null);
    } catch {
      setCouncilRound(null);
    }
  };

  const loadCouncilRounds = async () => {
    try {
      const r = await fetch(`${API}/api/council/rounds?limit=10`);
      const j = (await r.json()) as { ok: boolean; rounds?: CouncilRoundSummary[] };
      setCouncilRounds(j.ok ? j.rounds ?? [] : null);
    } catch {
      setCouncilRounds(null);
    }
  };

  // V5: the round itself runs on the sidecar's background job thread —
  // POST just starts it. This polls GET /api/council/job every 3s (same
  // interval as startPolling above) until it settles, then renders the
  // winner card / score table exactly as the old inline-await path did.
  const startCouncilPolling = useCallback(() => {
    stopCouncilPolling();
    councilPollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/council/job`);
        const j = (await r.json()) as { ok: boolean; job: CouncilJob };
        if (!j.ok) return;
        if (j.job.state === "done" || j.job.state === "error") {
          stopCouncilPolling();
          setCouncilBusy(false);
          if (j.job.state === "error") {
            setCouncilResult({ ok: false, error: j.job.error ?? "council job failed" });
            setCouncilNote(j.job.error ?? "council job failed");
          } else {
            setCouncilResult({
              ok: true,
              round_id: j.job.round_id ?? undefined,
              winner: j.job.winner ?? null,
              winner_mean: j.job.winner_mean ?? null,
              select_reason: j.job.select_reason ?? undefined,
            });
            if (j.job.round_id) void loadCouncilRound(j.job.round_id);
          }
          if (councilRoundsOpen) void loadCouncilRounds();
        }
      } catch {
        stopCouncilPolling();
        setCouncilBusy(false);
      }
    }, 3000);
  }, [stopCouncilPolling, councilRoundsOpen]);

  const onConvene = async () => {
    setCouncilBusy(true);
    setCouncilNote(null);
    setCouncilResult(null);
    setCouncilRound(null);
    try {
      const members: Record<string, string[]> = {};
      for (const tier of TIER_NAMES) {
        if (councilSelection[tier].length > 0) members[tier] = councilSelection[tier];
      }
      const res = await post("/api/council/convene", {
        placement: "planner",
        goal: councilGoal.trim() || undefined,
        members: Object.keys(members).length > 0 ? members : undefined,
      });
      if (res.ok && res.started) {
        startCouncilPolling(); // councilBusy stays true until the job settles
      } else {
        setCouncilNote(res.error ?? "council convene failed");
        setCouncilBusy(false);
      }
    } catch {
      setCouncilNote("council convene failed — is the admin sidecar running?");
      setCouncilBusy(false);
    }
  };

  const onReject = async () => {
    setBusy("reject");
    setCouncilNote(null);
    setCouncilResult(null);
    setCouncilRound(null);
    // V5: the revert stays synchronous — its result is in this response —
    // but the E3 council (if started) settles later on the job slot.
    const res = await post("/api/selfedit/reject");
    if (res.ok) {
      setNote(`session reverted to ${res.reverted?.reverted_to ?? "rollback point"}`);
      setChecks(null);
      setSummary(null);
      if (res.council_started) {
        setCouncilBusy(true);
        startCouncilPolling();
      } else {
        setCouncilNote("session reverted; no council brief available for this rejection");
      }
    } else {
      setNote(res.error ?? "reject failed");
    }
    void refresh();
    setBusy(null);
  };

  // --- planning pathway (P7) ---------------------------------------------
  // Same "POST starts a background job, GET polls it" shape as the self-
  // edit run and council convene above — one more instance of the sidecar's
  // established job-slot pattern, not a new one.

  const startPlanPolling = useCallback(() => {
    stopPlanPolling();
    planPollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/plan/job`);
        const j = (await r.json()) as { ok: boolean; job: PlanJob };
        if (!j.ok) return;
        setPlanJob(j.job);
        if (j.job.state !== "running") stopPlanPolling();
      } catch {
        stopPlanPolling();
      }
    }, 3000);
  }, [stopPlanPolling]);

  const onPlanStart = async () => {
    setPlanNote(null);
    const reviewPath = planReviewPath.trim();
    try {
      const res = await post("/api/plan/start", {
        goal: planGoal,
        mode: planMode,
        profile: planMode === "single" ? planProfile || undefined : undefined,
        review_path: reviewPath,
      });
      if (res.ok && res.started) {
        setPlanJob({
          state: "running", mode: planMode, goal: planGoal,
          review_path: reviewPath || null,
        });
        startPlanPolling();
      } else {
        setPlanNote(res.error ?? "could not start the planning job");
      }
    } catch {
      setPlanNote("planning job failed to start — is the admin sidecar running?");
    }
  };

  const onPlanChoose = async (label: string) => {
    setPlanNote(null);
    const res = await post("/api/plan/choose", { label });
    if (res.ok) {
      try {
        const r = await fetch(`${API}/api/plan/job`);
        const j = (await r.json()) as { ok: boolean; job: PlanJob };
        if (j.ok) setPlanJob(j.job);
      } catch {
        /* the choice was still recorded server-side; just can't refresh */
      }
    } else {
      setPlanNote(res.error ?? "could not record that choice");
    }
  };

  const onPlanAdopt = async () => {
    setPlanNote(null);
    const res = await post("/api/plan/adopt", { path: planAdoptPath || undefined });
    if (res.ok && res.saved_to_sandbox === true) {
      setPlanNote(
        `Saved at ${res.path ?? "the plan path"} in the sandbox. ` +
          "Finish the self-edit session to verify it and prepare a draft PR.",
      );
    } else {
      setPlanNote(res.error ?? "The server did not confirm a sandbox save. Check self-edit status before retrying.");
    }
  };

  const onPlanStartSelfEdit = async () => {
    setPlanNote(null);
    setBusy("run");
    setNote(null);
    setPrUrl(null);
    try {
      const res = await post("/api/selfedit/run", {
        goal: planJob.goal ?? "",
        plan: planJob.plan ?? undefined,
      });
      if (res.ok && res.started) {
        setNote(`planning with ${res.profile} — this can take several minutes…`);
        startPolling();
      } else {
        setNote(res.error ?? "could not start the run");
        setBusy(null);
      }
    } catch {
      setNote("agent run failed — is the admin sidecar running?");
      setBusy(null);
    }
  };

  const onPlanCancel = async () => {
    stopPlanPolling();
    await post("/api/plan/cancel");
    setPlanJob(IDLE_PLAN_JOB);
    setPlanNote(null);
    setPlanReviewPath("");
  };

  if (unreachable) {
    return (
      <div className="editmode-panel">
        <div className="panel-title">Edit mode</div>
        <div className="git-offline">admin sidecar offline</div>
      </div>
    );
  }

  const active = status?.active ?? false;
  const running = busy === "run";

  return (
    <div className="editmode-panel">
      <div className="panel-title">Edit mode</div>
      <div className="editmode-disclaimer">
        Changes are proposed on a sandbox branch and opened as a pull request.
        Merging happens on GitHub, by you — never from here.
      </div>

      {active && status && (
        <div className="editmode-session">
          <span className="git-branch">⎇ {status.branch}</span>
          <span className="editmode-tag">rollback: {status.rollback_tag}</span>
        </div>
      )}

      {!active && (
        <>
          <select
            className="git-input"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            disabled={busy !== null}
            title="Planner model for this edit run"
          >
            {models.length === 0 && (
              <option value="">planner models unavailable</option>
            )}
            {models.map((m) => (
              <option key={m.name} value={m.name} disabled={!m.key_present}>
                {m.label}
                {m.default ? " (default)" : ""}
                {m.key_present ? "" : " — key missing"}
              </option>
            ))}
          </select>
          <div className="git-commit-row">
            <input
              className="git-input"
              placeholder="what should I change?"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              disabled={busy !== null}
            />
            <button
              type="button"
              className="btn btn-primary"
              onClick={onRun}
              disabled={busy !== null || !goal.trim()}
            >
              {running ? "Working…" : "Run upgrade agent"}
            </button>
          </div>
        </>
      )}

      {summary && <div className="editmode-summary">{summary}</div>}

      {active && status && status.proposals.length > 0 && (
        <div className="editmode-proposals">
          {status.proposals.map((p) => (
            <details key={p.path} className="editmode-proposal">
              <summary>
                {p.path} — {p.rationale}
              </summary>
              <pre className="editmode-diff">{p.diff}</pre>
            </details>
          ))}
        </div>
      )}

      {active && (
        <div className="editmode-actions">
          <button
            type="button"
            className="btn"
            onClick={onValidate}
            disabled={busy !== null || !status?.proposals.length}
          >
            {busy === "validate" ? "Validating…" : "Validate"}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onSubmit}
            disabled={busy !== null || !status?.validated_ok}
            title={status?.validated_ok ? "Open a pull request" : "Validate first"}
          >
            {busy === "submit" ? "Submitting…" : "Submit PR"}
          </button>
          <button
            type="button"
            className="btn editmode-revert"
            onClick={onRevert}
            disabled={busy !== null}
          >
            Revert session
          </button>
          {status && status.proposals.length > 0 && (
            <button
              type="button"
              className="btn editmode-reject"
              onClick={onReject}
              disabled={busy !== null}
              title="Reject this diff and ask the council for a better approach"
            >
              {busy === "reject" ? "Rejecting…" : "Reject + ask council"}
            </button>
          )}
        </div>
      )}

      {checks && (
        <div className="editmode-checks">
          {checks.map((c) => (
            <div key={c.name} className={c.ok ? "check-ok" : "check-fail"}>
              {c.ok ? "✓" : "✗"} {c.name}
              {!c.ok && <pre className="editmode-diff">{c.output}</pre>}
            </div>
          ))}
        </div>
      )}

      {prUrl && (
        <div className="editmode-pr">
          PR opened:{" "}
          <a href={prUrl} target="_blank" rel="noreferrer">
            {prUrl}
          </a>
          <div className="editmode-merge-note">{MERGE_NOTE}</div>
        </div>
      )}
      {note && <div className="git-note">{note}</div>}

      <div className="editmode-planning">
        <div className="panel-title">{planJob.review_path ? "Review" : "Planning"}</div>
        <div className="editmode-disclaimer">
          Drafts an implementation plan or spec — no files are touched.
          Covers interface upgrades, new apps, and standalone plans alike.
          Set a path below to review an existing document instead of
          authoring a new one.
        </div>

        <input
          className="git-input"
          placeholder="review an existing document (path, optional) — e.g. docs/plans/my-plan.md"
          value={planReviewPath}
          onChange={(e) => setPlanReviewPath(e.target.value)}
          disabled={planJob.state === "running"}
        />

        <div className="editmode-planning-mode">
          <label>
            <input
              type="radio"
              name="plan-mode"
              checked={planMode === "single"}
              onChange={() => setPlanMode("single")}
              disabled={planJob.state === "running"}
            />
            single model
          </label>
          <label>
            <input
              type="radio"
              name="plan-mode"
              checked={planMode === "council"}
              onChange={() => setPlanMode("council")}
              disabled={planJob.state === "running"}
            />
            council: parallel drafts
          </label>
        </div>

        {planMode === "single" && (
          <select
            className="git-input"
            value={planProfile}
            onChange={(e) => setPlanProfile(e.target.value)}
            disabled={planJob.state === "running"}
            title="Planner model to author the plan"
          >
            <option value="">default planner</option>
            {models.map((m) => (
              <option key={m.name} value={m.name} disabled={!m.key_present}>
                {m.label}
                {m.default ? " (default)" : ""}
                {m.key_present ? "" : " — key missing"}
              </option>
            ))}
          </select>
        )}

        <div className="git-commit-row">
          <input
            className="git-input"
            placeholder="what should the plan cover?"
            value={planGoal}
            onChange={(e) => setPlanGoal(e.target.value)}
            disabled={planJob.state === "running"}
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={onPlanStart}
            disabled={planJob.state === "running" || !planGoal.trim()}
          >
            {planJob.state === "running" ? "Drafting…" : "Start"}
          </button>
        </div>

        {planNote && <div className="git-note">{planNote}</div>}

        {planJob.state === "error" && (
          <div className="editmode-planning-error">{planJob.error}</div>
        )}

        {planJob.state === "awaiting_choice" && planJob.candidates && (
          <div className="editmode-planning-candidates">
            {planJob.candidates.map((c) => (
              <details key={c.label} className="editmode-planning-candidate">
                <summary>
                  {c.label} — {c.profile}
                  {c.advisory_mean != null && ` (advisory ${c.advisory_mean.toFixed(1)})`}
                </summary>
                <pre className="editmode-diff">{c.content}</pre>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void onPlanChoose(c.label)}
                >
                  Choose this plan
                </button>
              </details>
            ))}
          </div>
        )}

        {planJob.state === "done" && (
          <div className="editmode-planning-done">
            <div className="editmode-council-reason">
              {planJob.review_path ? "reviewed" : "drafted"} by {planJob.author}
              {planJob.review_path && ` — ${planJob.review_path}`}
            </div>
            <pre className="editmode-diff">{planJob.plan}</pre>
            <div className="git-commit-row">
              <input
                className="git-input"
                placeholder={
                  planJob.review_path
                    ? "docs/reviews/….md (optional)"
                    : "docs/plans/….md (optional)"
                }
                value={planAdoptPath}
                onChange={(e) => setPlanAdoptPath(e.target.value)}
              />
              <button type="button" className="btn" onClick={onPlanAdopt}>
                Save in sandbox
              </button>
            </div>
            {!planJob.review_path && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void onPlanStartSelfEdit()}
                disabled={busy !== null}
              >
                Start self-edit with this plan
              </button>
            )}
          </div>
        )}

        {planJob.state !== "idle" && (
          <button type="button" className="btn editmode-revert" onClick={() => void onPlanCancel()}>
            Cancel
          </button>
        )}
      </div>

      <div className="editmode-council">
        <div className="panel-title">LLM Council</div>
        <div className="editmode-disclaimer">
          Convenes on validation failure automatically, or on request here.
          A council ranks and advises — it never authors a diff itself.
        </div>

        <details className="editmode-council-members">
          <summary>Council membership</summary>
          {TIER_NAMES.map((tier) => (
            <div key={tier} className="editmode-council-tier">
              <div className="editmode-council-tier-name">{tier}</div>
              {modelsByTier(tier).length === 0 && (
                <div className="editmode-council-empty">no {tier}-tier profiles configured</div>
              )}
              {modelsByTier(tier).map((m) => (
                <label key={m.name} className="editmode-council-checkbox">
                  <input
                    type="checkbox"
                    checked={councilSelection[tier].includes(m.name)}
                    disabled={!m.key_present}
                    onChange={() => toggleCouncilMember(tier, m.name)}
                  />
                  {m.label}
                  {m.key_present ? "" : " — key missing"}
                </label>
              ))}
              {tierSelectionInvalid(tier) && (
                <div className="editmode-council-warning">
                  select at least 2, or none (none = use the full tier)
                </div>
              )}
            </div>
          ))}
        </details>

        <div className="git-commit-row">
          <input
            className="git-input"
            placeholder={
              active && status?.goal
                ? `optional — defaults to "${status.goal}"`
                : "what should the council plan for?"
            }
            value={councilGoal}
            onChange={(e) => setCouncilGoal(e.target.value)}
            disabled={councilBusy}
          />
          <button
            type="button"
            className="btn"
            onClick={onConvene}
            disabled={councilBusy || anyCouncilSelectionInvalid || (!active && !councilGoal.trim())}
            title={anyCouncilSelectionInvalid ? "fix an invalid tier selection above first" : undefined}
          >
            {councilBusy ? "Convening…" : "Convene the council"}
          </button>
        </div>

        {councilNote && <div className="git-note">{councilNote}</div>}

        {councilResult?.ok && (
          <div className="editmode-council-result">
            {councilResult.winner ? (
              <>
                <div className="editmode-council-winner">
                  winner: {councilResult.winner.profile}
                  {councilResult.winner_mean != null && ` (mean ${councilResult.winner_mean.toFixed(1)})`}
                </div>
                <div className="editmode-council-reason">{councilResult.select_reason}</div>
                <pre className="editmode-diff">{councilResult.winner.content}</pre>
              </>
            ) : (
              <div className="editmode-council-reason">
                no winner — {councilResult.select_reason ?? "the round did not select a proposal"}
              </div>
            )}
          </div>
        )}

        {councilRound?.scores && councilRound.scores.length > 0 && (
          <div className="editmode-council-roster">
            Proposers:{" "}
            {[...new Set(councilRound.scores.map((s) => s.proposal_profile))].join(", ")}
            {" · "}
            Judges:{" "}
            {[
              ...new Set(
                councilRound.scores.filter((s) => !s.shadow).map((s) => s.judge_profile),
              ),
            ].join(", ") || "—"}
            {councilRound.scores.some((s) => s.shadow) && (
              <>
                {" · "}
                Shadow:{" "}
                {[
                  ...new Set(
                    councilRound.scores.filter((s) => s.shadow).map((s) => s.judge_profile),
                  ),
                ].join(", ")}
              </>
            )}
          </div>
        )}

        {councilRound?.scores && councilRound.scores.length > 0 && (
          <table className="editmode-council-scores">
            <thead>
              <tr>
                <th>judge</th>
                <th>tier</th>
                <th>proposal</th>
                <th>score</th>
                <th>justification</th>
              </tr>
            </thead>
            <tbody>
              {councilRound.scores.map((s, i) => (
                <tr key={i} className={s.shadow ? "editmode-council-shadow-row" : undefined}>
                  <td>
                    {s.judge_profile}
                    {s.shadow ? " (shadow)" : ""}
                  </td>
                  <td>{s.judge_tier}</td>
                  <td>{s.proposal_profile}</td>
                  <td>{s.score != null ? s.score.toFixed(1) : "abstained"}</td>
                  <td>{s.score != null ? s.justification : s.abstain_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <details
          className="editmode-council-rounds"
          open={councilRoundsOpen}
          onToggle={(e) => {
            const open = (e.target as HTMLDetailsElement).open;
            setCouncilRoundsOpen(open);
            if (open) void loadCouncilRounds();
          }}
        >
          <summary>Recent rounds</summary>
          {councilRounds === null && (
            <div className="editmode-council-empty">could not load rounds</div>
          )}
          {councilRounds?.length === 0 && (
            <div className="editmode-council-empty">no rounds yet</div>
          )}
          {councilRounds && councilRounds.length > 0 && (
            <table className="editmode-council-rounds-table">
              <thead>
                <tr>
                  <th>when</th>
                  <th>trigger</th>
                  <th>tier</th>
                  <th>status</th>
                  <th>winner</th>
                  <th>retry</th>
                </tr>
              </thead>
              <tbody>
                {councilRounds.map((r) => (
                  <tr
                    key={r.round_id}
                    className="editmode-council-rounds-row"
                    onClick={() => void loadCouncilRound(r.round_id)}
                  >
                    <td>{new Date(r.started_at).toLocaleString()}</td>
                    <td>{r.trigger}</td>
                    <td>{r.tier}</td>
                    <td>{r.status}</td>
                    <td>{r.winner_profile ?? "—"}</td>
                    <td>
                      {r.retry_validated === null
                        ? "—"
                        : r.retry_validated
                        ? "✓"
                        : "✗"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </details>
      </div>
    </div>
  );
}
