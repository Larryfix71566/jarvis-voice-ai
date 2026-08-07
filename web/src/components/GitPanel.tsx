import { useCallback, useEffect, useState } from "react";

const API = "http://localhost:7861";

interface Status {
  branch: string;
  clean: boolean;
  changed_files: string[];
  ahead: number;
  behind: number;
}

interface Draft {
  ok: boolean;
  action_id?: number;
  summary?: string;
  error?: string;
}

export default function GitPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pushDraft, setPushDraft] = useState<Draft | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/git/status`);
      setStatus(await r.json());
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const post = async (path: string, body?: object): Promise<Draft> => {
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.json();
  };

  const onPrepareCommit = async () => {
    setNote(null);
    setDraft(await post("/api/git/prepare-commit", { message }));
  };

  const onConfirmCommit = async () => {
    if (!draft?.action_id) return;
    const res = await post("/api/git/commit", { action_id: draft.action_id });
    setNote(res.ok ? "Committed." : res.error ?? "commit failed");
    setDraft(null);
    setMessage("");
    void refresh();
  };

  const onPreparePush = async () => {
    setNote(null);
    setPushDraft(await post("/api/git/prepare-push"));
  };

  const onConfirmPush = async () => {
    if (!pushDraft?.action_id) return;
    const res = await post("/api/git/push", { action_id: pushDraft.action_id });
    setNote(res.ok ? "Pushed." : res.error ?? "push failed");
    setPushDraft(null);
    void refresh();
  };

  if (unreachable) {
    return (
      <div className="git-panel">
        <div className="panel-title">Repository</div>
        <div className="git-offline">admin sidecar offline</div>
      </div>
    );
  }

  return (
    <div className="git-panel">
      <div className="panel-title">Repository</div>
      {status && (
        <div className="git-status">
          <span className="git-branch">⎇ {status.branch}</span>
          <span className={status.clean ? "git-clean" : "git-dirty"}>
            {status.clean ? "clean" : `${status.changed_files.length} changed`}
          </span>
          {status.ahead > 0 && <span className="git-ahead">↑{status.ahead}</span>}
          {status.behind > 0 && <span className="git-behind">↓{status.behind}</span>}
        </div>
      )}

      {draft?.ok ? (
        <div className="git-draft">
          <div className="git-draft-summary">{draft.summary}</div>
          <div className="git-draft-actions">
            <button type="button" className="btn btn-primary" onClick={onConfirmCommit}>
              Confirm commit
            </button>
            <button type="button" className="btn" onClick={() => setDraft(null)}>
              Discard
            </button>
          </div>
        </div>
      ) : (
        <div className="git-commit-row">
          <input
            className="git-input"
            placeholder="commit message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={!status || status.clean}
          />
          <button
            type="button"
            className="btn"
            onClick={onPrepareCommit}
            disabled={!status || status.clean || !message.trim()}
          >
            Draft
          </button>
        </div>
      )}
      {draft && !draft.ok && <div className="git-note">{draft.error}</div>}

      {pushDraft?.ok ? (
        <div className="git-draft">
          <div className="git-draft-summary">{pushDraft.summary}</div>
          <div className="git-draft-actions">
            <button type="button" className="btn btn-primary" onClick={onConfirmPush}>
              Confirm push
            </button>
            <button type="button" className="btn" onClick={() => setPushDraft(null)}>
              Discard
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="btn git-push"
          onClick={onPreparePush}
          disabled={!status || status.ahead === 0}
        >
          Push
        </button>
      )}
      {pushDraft && !pushDraft.ok && <div className="git-note">{pushDraft.error}</div>}
      {note && <div className="git-note">{note}</div>}
    </div>
  );
}
