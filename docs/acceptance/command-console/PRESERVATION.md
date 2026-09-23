# Preservation matrix

The Command Console is additive. The existing Output, Log, Memory, Repo,
Edit, Runs, Agents, and Costs tabs remain owned by `DrawerView`; WorkspaceStore
continues to own result identity, pins, comparison, and reading state. The
legacy layout remains selectable through the Debug menu. Any row requiring a
physical screen or user acceptance remains open until exercised on the Mac.

- [x] Shared action enum and protocol reject unknown actions.
- [x] Stale revisions and duplicate request IDs are deterministic.
- [x] Existing result history and graph stores remain the source of truth.
- [x] Compact conversation startup and two-speaker wave tests pass.
- [x] Layout-2 navigation, result selection/comparison, Atlas selection,
  sharing controls, and primary graph selection use the shared coordinator;
  focused coordinator and graph-rendering tests pass.
- [ ] Full P0/C8/T1.3 preservation receipt for the frozen candidate.
