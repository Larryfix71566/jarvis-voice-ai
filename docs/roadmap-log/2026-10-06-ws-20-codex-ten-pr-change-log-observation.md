---
date: 2026-10-06
system: codex
rows: [WS-20]
prs: [160, 161, 162, 163, 165, 166, 167, 168, 164, 169, 170, 185]
---

Codex and an independent review agent verified the first ten actual published PR merges after B1 migration #160 (`30fa3db`), in first-parent merge order: #161, #162, #163, #165, #166, #167, #168, #164, #169, #170. This closes the ten-PR published-history change-log observation in the joint-working plan; checker warn-only/strict rollout and product/live acceptance remain open.

For each exact published pair of merge parents, `git merge-tree --write-tree <merge>^1 <merge>^2` exits zero and reconstructs the complete published tree. ROADMAP §8 stays byte-identical to B1's pointer/rule section at every merge. Both published non-main integration merges contributing to the window were replayed too: `60be4a8` is clean; `1bc84a1` reproduces a genuine ROADMAP conflict in WS-05 row fields, while §8 and the entire dated-log directory remain clean and match the published state. This positive control separates row conflicts from the change-log conflict criterion.

The proof concerns the actual published ten-PR window and its recorded merge history; it does not claim knowledge of erased, rebased or unpublished manual attempts. No source refs, product code, CI mode, deployment, provider or acceptance gate outside this observation was changed. The root audit receipt is embedded verbatim below; the independent audit reached the same result.

```json
{
  "version": "ws20-published-merge-observation-v1",
  "baseline": "30fa3db25a5e1d5edf74e6d73c883bfa0e9bc2f4",
  "source_main": "a4ad5a4488a5e8a3fe56d4c8741475577d8438fe",
  "git_version": "git version 2.54.0 (Apple Git-157)",
  "window": [
    {
      "pr": 161,
      "merge": "eacf99b30a5362088ee752f29663449a640c39e8",
      "parents": [
        "30fa3db25a5e1d5edf74e6d73c883bfa0e9bc2f4",
        "52112e6a08ccb5e5b1cf7f8353137034231050c8"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 162,
      "merge": "30ac2c7d4e228e2005330f939788d695e3116798",
      "parents": [
        "eacf99b30a5362088ee752f29663449a640c39e8",
        "673d2f4d69cf0b82ca6ec4e26abb52fd48607b28"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 163,
      "merge": "bd41b5edcdc594ad1eb34b51a12f16c37b6bb7be",
      "parents": [
        "30ac2c7d4e228e2005330f939788d695e3116798",
        "f3af7122f18aea0ea0a51e206884721593a61bb5"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 165,
      "merge": "ecdf3a3687a4ebbc6fb5269c0160f5d2e567fbb4",
      "parents": [
        "bd41b5edcdc594ad1eb34b51a12f16c37b6bb7be",
        "a0ad1b287edff7692e98c506b65ff2cd35987993"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 166,
      "merge": "1ada0111dc8db7a6c8a613a737d82aa73ed106d9",
      "parents": [
        "ecdf3a3687a4ebbc6fb5269c0160f5d2e567fbb4",
        "6e8bb9c859428651fe6535265fcf2ed9bbc5122c"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 167,
      "merge": "70e50542d5815668fa888f252f43e0f1caafee2d",
      "parents": [
        "1ada0111dc8db7a6c8a613a737d82aa73ed106d9",
        "f7c5f55e3e5729106b1ca07a47c664486f66681a"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 168,
      "merge": "2f4104ee51392f4749df75bc1c8de566dcc1d592",
      "parents": [
        "70e50542d5815668fa888f252f43e0f1caafee2d",
        "c2f83ea1919376a8487b895656efdd909e585c84"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 164,
      "merge": "954564183a31f7d20dc1bd3527a3d56a19a0b6fc",
      "parents": [
        "2f4104ee51392f4749df75bc1c8de566dcc1d592",
        "16c98fef75c3075f6dea61901070c0ee6620a650"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 169,
      "merge": "63aaeef0ed44163d619fe269d018554d6cfc682a",
      "parents": [
        "954564183a31f7d20dc1bd3527a3d56a19a0b6fc",
        "25c522949e2cb5a3874352d5d385bdd0667c6949"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    },
    {
      "pr": 170,
      "merge": "5679061e95d4dcaf1ba101a623dca3c9cc35a89d",
      "parents": [
        "63aaeef0ed44163d619fe269d018554d6cfc682a",
        "4c0b6a213f7c4a50243ddb93ffbfc54718382436"
      ],
      "replay_exit": 0,
      "roadmap_and_log_objects_match": true,
      "section8_unchanged": true,
      "complete_tree_matches_published": true
    }
  ],
  "positive_control": {
    "merge": "1bc84a1a24bbf0eacf970b3db5dea871defe06c7",
    "replay_exit": 1,
    "roadmap_conflict_detected": true,
    "section8_unchanged": true,
    "log_tree_matches_published": true
  },
  "passed": true,
  "scope": "First ten published PR merges after #160 and both published integration merges contributing to that window. Exact parent replay gives no conflict in docs/roadmap-log or ROADMAP \u00a78; one unrelated WS-05 row conflict is detected. Does not attest erased/rebased/unpublished manual history or close checker rollout/live product gates.",
  "integration_merges": [
    {
      "merge": "60be4a8f1b801c13f09b788f1bb59cdd587292bd",
      "parents": [
        "c8e983f3fd67a6e4adb4b1f09d6aaeb91356d550",
        "30fa3db25a5e1d5edf74e6d73c883bfa0e9bc2f4"
      ],
      "replay_exit": 0,
      "conflict_paths": [],
      "section8_unchanged": true,
      "log_tree_matches_published": true
    },
    {
      "merge": "1bc84a1a24bbf0eacf970b3db5dea871defe06c7",
      "parents": [
        "addf27835a4e7a2860e12b6e50dbb7bff14ac30f",
        "bd41b5edcdc594ad1eb34b51a12f16c37b6bb7be"
      ],
      "replay_exit": 1,
      "conflict_paths": [
        "ROADMAP.md"
      ],
      "section8_unchanged": true,
      "log_tree_matches_published": true
    }
  ],
  "section8_sha256": "62d34e09e176c65c1a1cfb035bc8ea30e665d984cc308a87ebe8b57f4edf964e"
}
```

Receipt SHA-256: `5db0a141966d2f2c948edc9d0dcbb3726cae6251c45c83c89185fe9f18c16ab5`.
