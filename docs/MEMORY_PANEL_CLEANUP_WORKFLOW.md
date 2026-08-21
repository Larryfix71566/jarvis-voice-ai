# Memory Panel Cleanup Workflow

**Purpose:** Keep the Memory panel focused on current work by auto-clearing finalized items and surfacing active items by urgency.

## Canonical behavior
- Automatically clear any item marked **archived**, **dismissed**, or **resolved** so the panel never displays them again.
- Show **unresolved review items at the top** (highest urgency/needs action) and **active live facts at the bottom** (lowest urgency/reference).
- The panel display is a live view derived from state; it should not require manual refresh beyond normal UI updates.

## Repeatable interaction pattern
- When the Memory panel renders or the underlying memory state changes, apply cleanup first (remove archived/dismissed/resolved), then order remaining items: unresolved review items → active live facts.
- Any future additions to memory item types must be slotted into this ordering without regressing the cleanup rule.

## QA checklist (use in PRs)
- After marking an item archived/dismissed/resolved, it disappears without a page reload.
- Unresolved review items appear above active live facts.
- Adding new item types preserves the cleanup rule and ordering.
