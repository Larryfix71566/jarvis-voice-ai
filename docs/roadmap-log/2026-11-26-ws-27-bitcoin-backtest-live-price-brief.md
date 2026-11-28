---
date: 2026-11-26
system: claude
rows: [WS-27]
prs: [426]
---
# WS-27 Bitcoin backtest, live price and Daily Brief additions

- **Change:** Plan §3.4 amended (documentation only). Option 2 gains a
  backtest of the recovery rule: the same calculator replayed over full
  Coin Metrics `PriceUSD` history with no look-ahead, a per-bear report of
  counts and sample size (never odds), a frozen rule with no tuning, and its
  tests, plus a second indicator under test: price against its 4-year
  average (200-week variant in the backtest only; total market cap optional
  and unbuilt), shown only as a context line. Option 3 gains a live price layer (Kraken public Ticker, Coinbase
  public ticker fallback, polled every 30 seconds only while the workspace is
  on screen, never fed into the calculator). The Daily Brief gains a progress
  line, a history clause on change days and a labelled last price that never
  delays the brief. The "no background monitoring" line changes only as far
  as open-workspace polling and single fetches.
- **Evidence:** Larry asked on 2026-11-26 for backtesting, live pricing as a
  graph, for the gains to reach the Daily Brief, and to add the 4-year
  average from a video he shared. A throwaway probe over the
  Coin Metrics CSV (2010-07-18 to 2026-05-23, no gaps) found seven bears at 50%
  or more below the prior closing high and a first qualifying signal after each
  low; it is not committed. Scope doc: "Bitcoin recovery-rule backtest: scope".
- **Left / next actor:** Implementation owners stay unassigned. First build
  step checks the Coin Metrics community API from Larry's Mac (unreachable
  from the cloud sandbox) and the two venues' terms at claim time. The WS-27
  row's text is left for the daily batch to fold this file into.
