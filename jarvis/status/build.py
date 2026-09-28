"""`app_build_status()` — was the Mac app rebuilt, and from which commit (spec T2.3).

Reads the bundle `macos/MortimerHost/scripts/bundle.sh` writes: its
modification time and the provenance keys it stamps into
`Contents/Info.plist`. Compares the bundle's source revision with the
checkout's HEAD (the one `git rev-parse HEAD` reader in
jarvis.status.services). Read-only.
"""

from __future__ import annotations

import plistlib
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.status.services import repo_head as _repo_head

APP_RELATIVE = Path("macos") / "MortimerHost" / ".build" / "MortimerHost.app"
PLIST_KEYS = ("MortimerSourceRevision", "MortimerSourceDirty", "MortimerBuildConfiguration")


def app_build_status(repo_root: Path | str, *,
                     head: Callable[[Path], str | None] = _repo_head) -> dict[str, Any]:
    root = Path(repo_root)
    app = root / APP_RELATIVE
    out: dict[str, Any] = {"ok": True, "app_path": str(APP_RELATIVE), "exists": app.exists()}
    out["modified_at"] = (
        datetime.fromtimestamp(app.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        if out["exists"] else None
    )
    info: dict[str, Any] = {}
    plist_path = app / "Contents" / "Info.plist"
    if plist_path.exists():
        try:
            with plist_path.open("rb") as fh:
                info = plistlib.load(fh)
        except Exception as exc:  # noqa: BLE001 — a corrupt plist is reported, not raised
            out["plist_error"] = type(exc).__name__
    for key in PLIST_KEYS:
        value = info.get(key)
        out[key] = str(value) if value is not None else None
    repo = head(root)
    out["repo_head"] = repo
    out["matches_repo_head"] = bool(repo and out["MortimerSourceRevision"] == repo)
    return out
