---
date: 2026-11-27
system: claude
rows: [WS-27, WS-13]
prs: [this PR]
---
# WS-27 and WS-13: Bitcoin dashboard with reference bands, and a sectioned brief

- **Change:** Documentation only. WS-27 plan §3.4 gains "Dashboard charts and
  reference bands": three charts (all-history cycle view on a log scale with
  the power-law corridor and rainbow zones; a 365-day stance view with the
  200-day average, the prior 84-day closing high and Mayer bands; a 90-day
  view with Bollinger Bands), each with labelled axes and tick values and one
  plain line saying where the close sits. The bands are reference only and
  never inputs to the stance, rule, backtest or brief stance. The fit method,
  zone count, Mayer multiples (0.8x, 2.4x) and Bollinger settings (20 closes,
  2 standard deviations) are proposed defaults open for Larry's decision, as
  is where the dashboard lives (default: the Option 3 workspace's first view).
  WS-13 plan gains §R.0g, revision 9: labelled sections in a fixed order, short
  lines readable at the narrowest window, and a host-owned control to the
  dashboard in place of a link, with mail kept off the dashboard. Section
  order is a proposed default.
- **Evidence:** Larry's messages in his Claude Duet channel on 2026-11-27
  (21:41:16, 21:43:05, 21:44:40, 21:46:03 and 21:47:05 UTC), quoted in both
  plan sections. A test stand-in of the brief and dashboard runs outside
  Mortimer as a prototype; it is not evidence that anything here works.
- **Left / next actor:** larry: decide the proposed defaults (band parameters,
  dashboard placement, section order). Implementation owners stay unassigned;
  the dashboard depends on WS-27 Option 3's versioned series payload, or on
  the carousel alternative if Larry picks it, and the brief's Bitcoin section
  needs a joint WS-27/WS-13 claim for the shared payload. Builds on PR 426,
  which this branch is stacked on. The rows' text is left for the daily batch.
