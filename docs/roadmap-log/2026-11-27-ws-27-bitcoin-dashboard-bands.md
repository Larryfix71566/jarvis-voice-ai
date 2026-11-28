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
  decision. A second subsection adds two daily brief lines: "days like
  today" (past stretches at a similar close-to-200-day ratio, scored "higher
  in N of M" at 30, 90 and 365 days, counts only, stated as not a forecast)
  and "levels to watch" (the 200-day average and the provisional low, both
  existing stance inputs). Band width, stretch gap, scoring day, horizons and
  the five-stretch floor are proposed defaults. A self-check fixture covers
  both lines (synthetic series plus the frozen 2026-11-23 fix).
  A third subsection adds a trend regime line: Bull after seven consecutive
  closes above the 200-day average, Bear after seven below, shown beside the
  stance and not an input to it (a decision left to Larry), with its own
  backtest report and self-check fixture. The seven-close hold and the labels
  are proposed defaults.
  Updated 2026-11-28: Larry chose every proposed default ("All defaults"),
  so the three subsections now record them as decided: the corridor's floor
  is a fit over every close shifted to the lowest close and its ceiling a fit
  through each halving cycle's highest close (matching the test dashboard,
  not the earlier single-fit draft), seven rainbow zones (not nine), Mayer
  0.8x/2.4x, Bollinger 20 closes and 2 standard deviations, the dashboard as
  the Option 3 workspace's first view, the days-like-today parameters, the
  seven-close regime hold, the regime as a label and not a stance input, and
  the labels Bull and Bear. The cycle view also gains halving markers: solid
  lines at the four halvings (blocks 210,000 to 840,000), dotted lines at the
  midpoints, and the next halving and latest midpoint marked estimated.
- **Evidence:** Larry's messages in his Claude Duet channel on 2026-11-27
  (21:41:16, 21:43:05, 21:44:40, 21:46:03, 21:47:05, 22:06:49, 23:02:21 and
  23:04:19 UTC) and on 2026-11-28 (15:31:27 UTC), quoted in the sections. The orientation figures in the new lines and the regime came from the channel's
  test stand-in and were not reproduced in this PR. A test stand-in of the dashboard runs outside Mortimer as a
  prototype; it is not evidence that anything here works.
- **Left / next actor:** larry: merge #426 before this PR, which is stacked
  on it. Implementation owners stay
  unassigned; the dashboard depends on Option 3's versioned series payload,
  as decided. The brief's layout and its
  dashboard control are WS-13, in #428. The row's text is left for the daily
  batch.
