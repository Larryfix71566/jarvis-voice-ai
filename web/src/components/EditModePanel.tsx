import { useCallback, useEffect, useState } from "react";

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

interface RunResult {
  ok: boolean;
  summary: string;
  status: SessionStatus;
}

interface Check {
  name: string;
  ok: boolean;
  output: string;
}

const MERGE_NOTE =
  "Review and merge on GitHub — Jarvis cannot merge this.";

export default function EditModePanel() {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/selfedit/status`);
      setStatus(await r.json());
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
      const res: RunResult = await post("/api/selfedit/run", { goal });
      setSummary(res.summary);
      setStatus(res.status);
    } catch {
      setNote("agent run failed — is the admin sidecar running?");
    }
    setBusy(null);
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

  if (unreachable) {
    return (
      <div className="editmode-panel">
        <div className="panel-title">Edit mode</div>
        <div className="git-offline">admin sidecar offline</div>
      </div>
    );
  }

  const active = status?.active ?? false;

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
            {busy === "run" ? "Working…" : "Run upgrade agent"}
          </button>
        </div>
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
    </div>
  );
}
