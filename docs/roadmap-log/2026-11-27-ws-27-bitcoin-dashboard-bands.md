---
date: 2026-11-27
system: claude
rows: [WS-27]
prs: [427]
---
# WS-27: Bitcoin dashboard with reference bands

- **Change:** Documentation only. Plan §3.4 gains "Dashboard charts and
  reference bands": three charts (all-history cycle view on a log scale with
  the power-law corridor and rainbow zones; a 365-day stance view with the
  200-day average, the prior 84-day closing high and Mayer bands; a 90-day
  view with Bollinger Bands), each with labelled axes and tick values and one
  plain line saying where the close sits. The bands are reference only and
  never inputs to the stance, rule, 4-year line, backtest or brief stance.
  The fit method, zone count, Mayer multiples (0.8x, 2.4x), Bollinger settings
  (20 closes, 2 standard deviations) and where the dashboard lives (default:
  the Option 3 workspace's first view) are proposed defaults open for Larry's
  decision.
- **Evidence:** Larry's messages in his Claude Duet channel on 2026-11-27
  (21:41:16, 21:43:05, 21:44:40, 21:46:03 and 21:47:05 UTC), quoted in the
  section. A test stand-in of the dashboard runs outside Mortimer as a
  prototype; it is not evidence that anything here works.
- **Left / next actor:** larry: decide the proposed defaults, then merge #426
  before this PR, which is stacked on it. Implementation owners stay
  unassigned; the dashboard depends on Option 3's versioned series payload,
  or on the carousel alternative if Larry picks it. The brief's layout and its
  dashboard control are WS-13, in #428. The row's text is left for the daily
  batch.
