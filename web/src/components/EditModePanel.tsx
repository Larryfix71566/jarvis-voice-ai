import { useCallback, useEffect, useRef, useState } from "react";

const ADMIN = "http://127.0.0.1:7861";

interface Proposal {
  path: string;
  rationale: string;
  diff: string;
}

interface SessionStatus {
  ok: boolean;
  active?: boolean;
  goal?: string;
  branch?: string;
  proposals?: Proposal[];
  validated_ok?: boolean;
  checks?: { name: string; ok: boolean; output: string }[];
  pr_url?: string;
  error?: string;
}

interface ModelProfile {
  name: string;
  label: string;
  provider: string;
  model: string;
  key_env: string;
  key_present: boolean;
  default: boolean;
}

interface RunJob {
  state: "idle" | "running" | "done" | "error";
  goal?: string | null;
  profile?: string | null;
  summary?: string | null;
}

export default function EditModePanel({ onClose }: { onClose: () => void }) {
  const [goal, setGoal] = useState("");
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState<"" | "run" | "validate" | "submit" | "revert">("");
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [profile, setProfile] = useState("");
  const [job, setJob] = useState<RunJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${ADMIN}/api/selfedit/status`, { method: "GET" });
      const j = (await r.json()) as SessionStatus;
      setStatus(j);
    } catch {
      setSummary("The admin sidecar looks offline — start the stack with ./scripts/mortimer.sh");
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const r = await fetch(`${ADMIN}/api/selfedit/models`);
      const j = (await r.json()) as { ok: boolean; models: ModelProfile[] };
      if (j.ok) {
        setModels(j.models);
        const dflt = j.models.find((m) => m.default && m.key_present) ?? j.models.find((m) => m.key_present);
        if (dflt) setProfile(dflt.name);
      }
    } catch {
      /* offline message already surfaced by refresh() */
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
        const r = await fetch(`${ADMIN}/api/selfedit/run`);
        const j = (await r.json()) as { ok: boolean; job: RunJob };
        if (!j.ok) return;
        setJob(j.job);
        if (j.job.state !== "running") {
          stopPolling();
          setBusy("");
          setSummary(j.job.summary ?? "");
          refresh();
        }
      } catch {
        stopPolling();
        setBusy("");
      }
    }, 3000);
  }, [refresh, stopPolling]);

  useEffect(() => {
    refresh();
    loadModels();
    return stopPolling;
  }, [refresh, loadModels, stopPolling]);

  const onRun = async () => {
    if (!goal.trim()) return;
    setBusy("run");
    setSummary("");
    try {
      const r = await fetch(`${ADMIN}/api/selfedit/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: goal.trim(), profile: profile || undefined }),
      });
      const j = await r.json();
      if (j.ok && j.started) {
        setJob({ state: "running", goal: goal.trim(), profile: j.profile });
        setSummary(`Planning with ${j.profile} — this can take several minutes…`);
        startPolling(); // busy stays "run" until the job settles
      } else {
        setSummary(j.error ?? "could not start the run");
        setBusy("");
      }
    } catch {
      setSummary("The admin sidecar looks offline — start the stack with ./scripts/mortimer.sh");
      setBusy("");
    }
  };

  const post = async (what: "validate" | "submit" | "revert") => {
    setBusy(what);
    try {
      const r = await fetch(`${ADMIN}/api/selfedit/${what}`, { method: "POST" });
      const j = await r.json();
      if (what === "validate") {
        setSummary(
          j.ok
            ? "Validation passed — ready to submit when you are."
            : `Validation failed: ${j.error ?? (j.checks ?? []).filter((c: { ok: boolean }) => !c.ok).map((c: { name: string; output: string }) => `${c.name}: ${c.output}`).join(" | ")}`
        );
      } else if (what === "submit") {
        setSummary(j.ok ? `Pull request opened: ${j.pr_url} — merging stays with you on GitHub.` : j.error ?? "submit failed");
      } else {
        setSummary(j.ok ? "Session reverted — the repo is back to a clean state." : j.error ?? "revert failed");
      }
      refresh();
    } catch {
      setSummary("The admin sidecar looks offline — start the stack with ./scripts/mortimer.sh");
    }
    setBusy("");
  };

  const running = busy === "run" || job?.state === "running";

  return (
    <div className="editmode-panel">
      <div className="editmode-head">
        <span>EDIT MODE</span>
        <button className="git-x" onClick={onClose}>✕</button>
      </div>

      <select
        className="git-input"
        value={profile}
        onChange={(e) => setProfile(e.target.value)}
        disabled={running}
        title="Planner model for this edit run"
      >
        {models.length === 0 && <option value="">planner models unavailable</option>}
        {models.map((m) => (
          <option key={m.name} value={m.name} disabled={!m.key_present}>
            {m.label}
            {m.default ? " (default)" : ""}
            {m.key_present ? "" : " — key missing"}
          </option>
        ))}
      </select>

      <textarea
        className="editmode-goal"
        placeholder="What should I change? e.g. add a clock panel to the command deck"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        disabled={running}
      />
      <button className="git-btn" onClick={onRun} disabled={running || !goal.trim()}>
        {running ? "⟳ agent working…" : "Run upgrade"}
      </button>

      {summary && <div className="editmode-summary">{summary}</div>}

      {status?.active && (
        <div className="editmode-session">
          <div className="editmode-sub">session: {status.branch}</div>
          {(status.proposals ?? []).map((p) => (
            <details key={p.path} className="editmode-prop">
              <summary>
                {p.path} — {p.rationale}
              </summary>
              <pre>{p.diff}</pre>
            </details>
          ))}
          <div className="editmode-actions">
            <button className="git-btn" disabled={running || busy !== ""} onClick={() => post("validate")}>
              Validate
            </button>
            <button className="git-btn" disabled={running || busy !== "" || !status.validated_ok} onClick={() => post("submit")}>
              Submit PR
            </button>
            <button className="git-btn git-danger" disabled={running || busy !== ""} onClick={() => post("revert")}>
              Revert
            </button>
          </div>
          {status.pr_url && <div className="editmode-sub">PR: {status.pr_url}</div>}
        </div>
      )}
    </div>
  );
}
