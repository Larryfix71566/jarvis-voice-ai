#!/usr/bin/env python3
"""Run Mortimer's daily new-model check by hand (WS-41).

The same check runs every morning inside `python -m jarvis.status.daily`
(launchd `com.mortimer.status-daily`, 06:30). It never uses an API key and
never switches a model; a model that passes certification becomes a pull
request into `next` (or a patch file when no GitHub token is set).

    python scripts/sync_models.py --detect-only   # public pages + pins, no probes, no PRs
    python scripts/sync_models.py --no-propose    # also probes and certifies, opens no PR
    python scripts/sync_models.py                 # the full daily run

Prints the report as JSON. Exit code is 0 unless the run itself failed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detect-only", action="store_true",
                        help="no Claude alias probes, no certification, no proposals")
    parser.add_argument("--no-propose", action="store_true", help="certify but open no PR")
    parser.add_argument("--status-dir", type=Path, default=None,
                        help="where model-sync.json is written (default data/status)")
    parser.add_argument("--quiet-notice", action="store_true",
                        help="do not queue the spoken notice")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        from jarvis.vault import inject_env

        inject_env()  # GitHub token for proposals; no model API key is used
    except Exception as exc:  # noqa: BLE001
        logging.warning("vault unavailable (%s); proposals fall back to a patch file",
                        type(exc).__name__)
    from jarvis.model_sync.run import STATUS_DIR, run_daily

    report = run_daily(
        args.status_dir or STATUS_DIR,
        probe_aliases=not args.detect_only,
        certify=False if args.detect_only else None,
        propose=False if (args.detect_only or args.no_propose) else None,
        notice=(lambda *_a: -1) if args.quiet_notice else None,  # -1: retried tomorrow
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
