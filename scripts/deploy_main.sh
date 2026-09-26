#!/bin/bash
# DEPLOY-MAIN: deploy GitHub main to production (~/jarvis-voice-ai-clean).
# Run it from any checkout of this repository, production included:
#   bash scripts/deploy_main.sh                        full verification
#   bash scripts/deploy_main.sh --reuse-verification   reuse an earlier passing run on the same commit
# Mortimer names it "DEPLOY-MAIN" after every merge. It moved here from the
# git-ignored closure-checks/DEPLOY-MAIN.sh on 2026-09-26 (Larry's decision of
# 2026-09-25) and is human-only (config/self_edit_allowlist.json deny).
# Phases, each gated; nothing in production changes until phase C:
#   A verify  -- build + all three test suites on the exact target, in a throwaway worktree
#   B snapshot-- rollback folder: live DB backups, code tarball, current app bundle, ROLLBACK.sh
#   C install -- production checkout -> target, build the app there (services untouched so far)
#   D switch  -- quit app, restart the 5 services, health checks, open production app, receipt
# Logs, receipts and verification worktrees go under ~/MortimerRollback.
# Runs as you (your git, your gh, your launchd). Prints no secrets.
#
# The whole script is one function, called on the last line. Phase C checks
# production out at the target, which replaces this file when it is run from
# production. Bash reads a script as it goes, so without the function it would
# go on reading the new file at the old offset. A function is parsed in full
# before it runs, and the last line is read before the call starts.
set -uo pipefail

main() {
  # A compiler or XCTest error, not a source excerpt that happens to contain
  # "error: " (LAUNCHER-RULES rule 9): ": error: " or "error: " at line start,
  # with or without colour codes.
  ERR_RE='(^|: )(.\[[0-9;]*m)*error: '
  HERE="$(cd "$(dirname "$0")/.." && pwd)"   # the checkout this script is in: production or any clone
  C="$HOME/jarvis-voice-ai-clean"
  PY="$C/.venv/bin/python"
  TS=$(date +%Y%m%d-%H%M%S)
  # Logs and verification worktrees live beside the rollback snapshots, outside
  # every checkout, so the script behaves the same wherever it is run from.
  RBROOT="$HOME/MortimerRollback"; LOGD="$RBROOT/logs"
  LOG="$LOGD/deploy-main-$TS.log"; mkdir -p "$LOGD" || { echo "cannot create $LOGD"; exit 1; }
  exec > >(tee -a "$LOG") 2>&1
  die() { echo; echo "STOPPED: $*"; echo "full log: $LOG"; exit 1; }
  say() { echo; echo "=== $* ==="; }
  UIDN=$(id -u)
  SERVICES="vault bot extractor admin costs"

  say "0. target"
  git -C "$HERE" fetch -q origin || die "fetch failed"
  TARGET=$(git -C "$HERE" rev-parse origin/main); SHORT=${TARGET:0:7}
  git -C "$HERE" log -1 --format='origin/main: %h %ad %s' --date=format:'%m-%d %H:%M' "$TARGET"
  git -C "$HERE" merge-base --is-ancestor 88b206f "$TARGET" || die "origin/main does not contain #80 (88b206f)"
  [ -x "$PY" ] || die "production venv python missing: $PY"
  # A zero-byte index.lock left by a crashed/sandboxed git blocks every checkout
  # (23 Sep: production had one dated 11 Sep). Remove it only when it is empty,
  # older than 10 minutes, and no git process is running; otherwise stop.
  LOCK="$C/.git/index.lock"
  if [ -e "$LOCK" ]; then
    if [ ! -s "$LOCK" ] && [ -n "$(find "$LOCK" -mmin +10 2>/dev/null)" ] && ! pgrep -x git >/dev/null; then
      echo "removing stale production lock: $(ls -l "$LOCK" | awk '{print $6,$7,$8}') (0 bytes, no git running)"
      rm -f "$LOCK" || die "could not remove $LOCK"
    else
      die "$LOCK exists and is not clearly stale (non-empty, recent, or git is running) -- check it by hand"
    fi
  fi
  echo "production before: $(git -C "$C" log -1 --format='%h' ) (+ $(git -C "$C" status --porcelain | wc -l | tr -d ' ') uncommitted entries)"
  # Production must hold no work that is not on main where the app build or the
  # services read. 24 Sep: Codex had 9 tracked edits and a half-applied
  # orb-crystal change in production. Phase C's `checkout -f` discarded the
  # tracked edits, the build then compiled the untracked CrystalGlassRig.swift
  # against the reverted JarvisConfig.swift and failed. Had it compiled, the
  # deploy would have shipped unreviewed Swift and dropped Codex's edits.
  # Untracked docs/, data/, logs/, tests/ and _to_delete/ are left alone.
  # P2-latency.json is the app's own latency report, rewritten on every run.
  DIRTY_TRACKED=$(git -C "$C" status --porcelain --untracked-files=no \
    | grep -v -x ' M docs/acceptance/adaptive-interface/P2-latency.json')
  UNTRACKED_CODE=$(git -C "$C" status --porcelain --untracked-files=all | sed -n 's/^?? //p' \
    | grep -E '^(macos/|jarvis/|mcp_servers/|services/|skills/|sandbox/|scripts/|config/|web/|requirements)')
  if [ -n "$DIRTY_TRACKED$UNTRACKED_CODE" ]; then
    echo "production holds work that is not on main:"
    { [ -n "$DIRTY_TRACKED" ] && echo "$DIRTY_TRACKED"; [ -n "$UNTRACKED_CODE" ] && sed 's/^/?? /' <<< "$UNTRACKED_CODE"; } | head -40 | sed 's/^/  /'
    die "move that work out of ~/jarvis-voice-ai-clean (commit it on a branch in its own worktree) before deploying -- nothing changed"
  fi

  # ---------------------------------------------------------------- A. verify
  # --reuse-verification: skip re-running the suites when an earlier run of THIS
  # script already passed all three on the SAME commit. The evidence is that
  # run's own log, named and quoted below, not a claim.
  if [ "${1:-}" = "--reuse-verification" ]; then
    PREV=$(grep -l "origin/main: $SHORT" "$LOGD"/deploy-main-*.log 2>/dev/null | while read f; do
             grep -qE "Executed [0-9]+ tests, with 0 failures" "$f" \
             && grep -qE "Executed [0-9]+ tests, with [0-9]+ tests skipped and 0 failures" "$f" \
             && grep -qE "^[0-9]+ passed, [0-9]+ skipped" "$f" && ! grep -qE "^[0-9]+ failed|STOPPED: .*(suite|pytest)" "$f" && echo "$f"; done | tail -1)
    [ -n "$PREV" ] || die "--reuse-verification: no earlier log shows all three suites passing on $SHORT"
    say "A. verification reused from $(basename "$PREV")"
    grep -E "^origin/main:|Executed [0-9]+ tests|^[0-9]+ passed" "$PREV" | sed 's/^[[:space:]]*/  /'
  else
  say "A. verify $SHORT in a throwaway worktree (no production change)"
  V="$(cd "$RBROOT" && pwd -P)/deploy-verify-$SHORT"      # absolute, no '..' (the first run compared the unnormalized path)
  if [ -e "$V" ]; then
    git -C "$HERE" worktree list --porcelain | grep -qx "worktree $V" || die "$V exists and is not a worktree of this repo -- move it aside"
    # Reuse it only if it is exactly the target and clean; its build is the one the
    # 23 Sep A/B and bisect runs passed on. Anything else is rebuilt from scratch.
    if [ "$(git -C "$V" rev-parse HEAD)" = "$TARGET" ] && [ -z "$(git -C "$V" status --porcelain)" ]; then
      echo "reusing verification worktree at $SHORT (clean)"
    else
      git -C "$HERE" worktree remove --force "$V" && echo "removed stale verification worktree"
    fi
  fi
  [ -d "$V" ] || git -C "$HERE" worktree add -q --detach "$V" "$TARGET" || die "worktree add failed"
  cd "$V"
  IMP=$(cd "$V" && "$PY" -c 'import jarvis,os;print(os.path.realpath(os.path.dirname(jarvis.__file__)))')
  case "$IMP" in "$V"/*) echo "python imports jarvis from the worktree: ok ($IMP)";; *) die "python imported jarvis from $IMP, not $V";; esac

  swift_gate() {  # $1 package dir, $2 label -- capture once, judge the suite's own final tally
    local out final
    out=$(cd "$V/$1" && swift test 2>&1); echo "$out" > "$LOGD/deploy-$2-$TS.txt"
    # No `echo | grep -q` under pipefail: grep -q exits at its first match and the
    # writer can die of SIGPIPE, turning a match into a non-zero pipeline (23 Sep:
    # a 250-test pass was stopped twice). Here-strings and [[ =~ ]] have no writer.
    final=$(grep -E 'Executed [0-9]+ tests?,' <<< "$out" | tail -1); echo "$final"
    if grep -qE "$ERR_RE" <<< "$out" || [[ "$final" =~ (with|and)\ [1-9][0-9]*\ failures? ]]; then
      grep -E "^Test Case .* failed|$ERR_RE" <<< "$out" | head -15; die "$2 suite failed"
    fi
    [[ "$final" =~ with\ ([0-9]+\ tests?\ skipped\ and\ )?0\ failures ]] || die "$2 suite produced no passing tally: $final"
  }
  echo "JarvisKit:";    swift_gate macos/JarvisKit jarviskit
  echo "MortimerHost:"; swift_gate macos/MortimerHost mortimerhost
  # tests/conftest.py isolates the vault so tests never see real credentials; a
  # credential exported in this shell walks straight past that (23 Sep: an
  # exported JARVIS_GITHUB_TOKEN made check_env probe GitHub, and an exported
  # model key let the real council convene inside test_upgrade_agent). Run the
  # suite with a minimal allowlisted environment instead. Names only are shown.
  echo "credential-shaped variables in this shell (names only; NOT passed to pytest):"
  echo "  $(env | grep -oE '^[A-Za-z0-9_]*(API_KEY|TOKEN|SECRET|PASSWORD|_KEY)[A-Za-z0-9_]*=' | tr -d = | sort | tr '\n' ' ')"
  echo "JARVIS_* variables in this shell (names only; NOT passed): $(env | grep -oE '^JARVIS_[A-Z0-9_]*=' | tr -d = | sort | tr '\n' ' ')"
  CLEAN_ENV=(env -i HOME="$HOME" PATH="$PATH" USER="${USER:-larryfix}" LOGNAME="${LOGNAME:-${USER:-larryfix}}"
             SHELL="${SHELL:-/bin/zsh}" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" TERM="${TERM:-xterm-256color}")
  echo "Python (clean environment, no .env sourced):"
  OUT=$(cd "$V" && "${CLEAN_ENV[@]}" "$PY" -m pytest -q -p no:cacheprovider 2>&1); RC=$?
  echo "$OUT" > "$LOGD/deploy-pytest-$TS.txt"; echo "$OUT" | tail -1
  [ $RC -eq 0 ] || { echo "$OUT" | grep -E "^FAILED|^ERROR" | head -15; die "pytest failed (exit $RC)"; }
  cd "$HERE"; git -C "$HERE" worktree remove --force "$V" && echo "verification worktree removed"
  fi

  # -------------------------------------------------------------- B. snapshot
  RB="$HOME/MortimerRollback/release-$SHORT-$TS"
  say "B. rollback snapshot -> $RB"
  mkdir -p "$RB" && chmod 700 "$RB" || die "cannot create $RB"
  PRIOR=$(git -C "$C" rev-parse HEAD)
  git -C "$C" status --porcelain > "$RB/prior-status.txt"
  git -C "$C" diff > "$RB/prior-tracked-changes.patch"
  "$PY" - "$C/data" "$RB" <<'PYB' || die "database backup failed"
import sqlite3, sys, hashlib, json, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
meta = {}
for name in ("jarvis.db", "costs.db"):
    s = src / name
    if not s.exists(): continue
    d = dst / name
    with sqlite3.connect(s) as a, sqlite3.connect(d) as b: a.backup(b)   # consistent online snapshot
    meta[name] = {"sha256": hashlib.sha256(d.read_bytes()).hexdigest(), "bytes": d.stat().st_size}
with sqlite3.connect(dst / "jarvis.db") as c:
    meta["conversations"] = c.execute("select count(*), max(id) from conversations").fetchone()
    meta["memories"] = c.execute("select count(*) from memories").fetchone()[0]
    meta["memories_columns"] = len(c.execute("pragma table_info(memories)").fetchall())
    meta["extraction_cursor"] = c.execute("select * from memory_extraction_cursor").fetchall()
(dst / "db-backup.json").write_text(json.dumps(meta, indent=1)); print(json.dumps(meta))
PYB
  tar -C "$C" --exclude ./.git --exclude ./.venv --exclude ./data --exclude ./logs \
      --exclude './macos/*/.build' --exclude '*/node_modules' --exclude '*/__pycache__' \
      -czf "$RB/code.tgz" . || die "code tarball failed"
  [ -d "$C/macos/MortimerHost/.build/MortimerHost.app" ] && ditto "$C/macos/MortimerHost/.build/MortimerHost.app" "$RB/MortimerHost.app"
  echo "code.tgz $(du -h "$RB/code.tgz" | cut -f1), prior HEAD ${PRIOR:0:7}, app bundle copied: $([ -d "$RB/MortimerHost.app" ] && echo yes || echo no)"
  cat > "$RB/ROLLBACK.sh" <<RBEOF
#!/bin/bash
# Restore production to its state before the $SHORT deploy of $TS.
# Code + app only by default. The database is NOT restored unless you pass --restore-db,
# because that discards every conversation and memory written since the deploy.
set -uo pipefail
C="$C"; RB="$RB"
osascript -e 'tell application id "com.mortimer.host" to quit' 2>/dev/null; sleep 3; pkill -x MortimerHost 2>/dev/null
git -C "\$C" checkout -q -f --detach $PRIOR || { echo "checkout of prior HEAD failed"; exit 1; }
tar -C "\$C" -xzf "\$RB/code.tgz" || { echo "code restore failed"; exit 1; }
rm -rf "\$C/macos/MortimerHost/.build/MortimerHost.app"; ditto "\$RB/MortimerHost.app" "\$C/macos/MortimerHost/.build/MortimerHost.app"
if [ "\${1:-}" = "--restore-db" ]; then
  for s in $SERVICES; do launchctl bootout gui/$UIDN/com.mortimer.\$s 2>/dev/null; done
  cp "\$RB/jarvis.db" "\$C/data/jarvis.db"; rm -f "\$C/data/jarvis.db-wal" "\$C/data/jarvis.db-shm"
  for s in $SERVICES; do launchctl bootstrap gui/$UIDN ~/Library/LaunchAgents/com.mortimer.\$s.plist; done
else
  for s in $SERVICES; do launchctl kickstart -k gui/$UIDN/com.mortimer.\$s; done
fi
sleep 8; open "\$C/macos/MortimerHost/.build/MortimerHost.app"; echo "rolled back to ${PRIOR:0:7} + prior local changes"
RBEOF
  chmod +x "$RB/ROLLBACK.sh"; echo "rollback script: $RB/ROLLBACK.sh"

  # --------------------------------------------------------------- C. install
  say "C. install $SHORT into production (services still on the old code in memory)"
  restore_code() {
    git -C "$C" checkout -q -f --detach "$PRIOR" && echo "git HEAD back on ${PRIOR:0:7}" || echo "WARNING: git checkout of ${PRIOR:0:7} failed -- files restored from the tarball only"
    tar -C "$C" -xzf "$RB/code.tgz" && echo "working files restored from $RB/code.tgz" || echo "WARNING: tarball restore reported errors -- see $RB"; }
  git -C "$C" fetch -q origin || die "production fetch failed"
  git -C "$C" checkout -q -f --detach "$TARGET" || { restore_code; die "production checkout failed"; }
  echo "production now: $(git -C "$C" log -1 --format='%h %s')"
  echo "left untracked (not on main, kept):"; git -C "$C" status --porcelain | sed 's/^/  /'
  echo "building app..."
  BUILD=$(cd "$C" && MORTIMER_BUNDLE_LAUNCH=0 MORTIMER_SOURCE_REVISION="$TARGET" bash macos/MortimerHost/scripts/bundle.sh debug 2>&1); BRC=$?
  echo "$BUILD" > "$LOGD/deploy-bundle-$TS.txt"; echo "$BUILD" | tail -3
  APPP="$C/macos/MortimerHost/.build/MortimerHost.app"
  REV=$(/usr/libexec/PlistBuddy -c 'Print :MortimerSourceRevision' "$APPP/Contents/Info.plist" 2>/dev/null)
  [ $BRC -eq 0 ] && [ "$REV" = "$TARGET" ] || {
    restore_code; rm -rf "$APPP"; ditto "$RB/MortimerHost.app" "$APPP"
    die "app build failed or bundle revision '$REV' != $TARGET -- production code and app restored; services were never restarted"; }
  echo "bundle revision: $REV"

  # ---------------------------------------------------------------- D. switch
  say "D. switch over"
  osascript -e 'tell application id "com.mortimer.host" to quit' 2>/dev/null; sleep 4
  pkill -x MortimerHost 2>/dev/null && sleep 2
  pgrep -x MortimerHost >/dev/null && die "an app instance is still running -- quit it and re-run from phase D by hand (see log)"
  for s in $SERVICES; do launchctl kickstart -k gui/$UIDN/com.mortimer.$s && echo "restarted $s"; done
  hcode() { curl -s -o /dev/null -m 3 -w '%{http_code}' "$1"; }
  ok=0
  for i in $(seq 1 30); do
    a=$(hcode http://127.0.0.1:7861/api/health); v=$(hcode http://127.0.0.1:8484/health); b=$(hcode http://127.0.0.1:7860/)
    if [ "$a" = 200 ] && [ "$v" = 200 ] && { [ "$b" = 307 ] || [ "$b" = 200 ]; }; then ok=1; break; fi; sleep 2
  done
  echo "health: admin=$a vault=$v bot=$b"
  [ $ok = 1 ] || { for s in bot admin vault; do echo "--- $s log tail"; tail -5 "$C/logs/$s.launchd.log"; done;
    die "services did not come healthy in 60 s. Code is deployed. To roll back code+app: $RB/ROLLBACK.sh"; }
  open "$APPP"; sleep 6

  "$PY" - "$C" "$RB" "$TARGET" "$LOGD" <<'PYD' || die "receipt failed"
import json, subprocess, sys, sqlite3, datetime, pathlib
C, RB, T, LOGS = sys.argv[1:5]; uid = subprocess.check_output(["id", "-u"], text=True).strip()
def pid(label):
    out = subprocess.run(["launchctl", "print", f"gui/{uid}/com.mortimer.{label}"], capture_output=True, text=True).stdout
    return next((int(l.split("=")[1]) for l in out.splitlines() if l.strip().startswith("pid =")), None)
def cwd(p):
    if not p: return None
    out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", str(p), "-Fn"], capture_output=True, text=True).stdout
    return next((l[1:] for l in out.splitlines() if l.startswith("n")), None)
procs = {}
for s in ("vault", "bot", "extractor", "admin", "costs"):
    p = pid(s); procs[s] = {"pid": p, "working_directory": cwd(p)}
app = subprocess.run(["pgrep", "-x", "MortimerHost"], capture_output=True, text=True).stdout.split()
exe = subprocess.run(["ps", "-o", "command=", "-p", app[0]], capture_output=True, text=True).stdout.strip() if app else None
procs["app"] = {"pid": int(app[0]) if app else None, "executable": exe}
with sqlite3.connect(f"file:{C}/data/jarvis.db?mode=ro", uri=True) as c:
    db = {"path": f"{C}/data/jarvis.db", "conversations": c.execute("select count(*),max(id) from conversations").fetchone(),
          "memories": c.execute("select count(*) from memories").fetchone()[0],
          "memories_columns": len(c.execute("pragma table_info(memories)").fetchall()),
          "extraction_cursor": c.execute("select * from memory_extraction_cursor").fetchall()}
# scripts/run_kb.sh cds into services/mortimer-vault by design (line 18), so a
# service is "in production" when its cwd is the checkout or a folder inside it.
inside = lambda d: bool(d) and (d == C or d.startswith(C + "/"))
problems = [f"{s} cwd is {v['working_directory']}" for s, v in procs.items() if s != "app" and not inside(v["working_directory"])]
if not exe or not exe.startswith(f"{C}/macos/MortimerHost/.build/MortimerHost.app/"): problems.append(f"app executable is {exe}")
r = {"status": "deployed" if not problems else "deployed-with-problems", "problems": problems,
     "deployed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
     "main_revision": T, "production_head": subprocess.check_output(["git", "-C", C, "rev-parse", "HEAD"], text=True).strip(),
     "bundle_source_revision": subprocess.check_output(["/usr/libexec/PlistBuddy", "-c", "Print :MortimerSourceRevision",
                                f"{C}/macos/MortimerHost/.build/MortimerHost.app/Contents/Info.plist"], text=True).strip(),
     "processes": procs, "database": db, "rollback": {"directory": RB, "script": f"{RB}/ROLLBACK.sh",
     "db_backup": json.loads(pathlib.Path(RB, "db-backup.json").read_text())}}
out = json.dumps(r, indent=1); pathlib.Path(RB, "deployment-receipt.json").write_text(out)
pathlib.Path(LOGS, f"deployment-receipt-{T[:7]}.json").write_text(out); print(out)
sys.exit(1 if problems else 0)
PYD
  say "DONE -- $SHORT deployed. Receipt in $RB and $LOGD. Rollback: $RB/ROLLBACK.sh"
}

main "$@"; exit $?
