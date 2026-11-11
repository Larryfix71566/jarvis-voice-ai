# Mortimer interface contracts (C0 and C0b)

- **Status:** draft for review in a PR into `next` (closure plan items C0 and C0b). Codex and Kimi review. Larry answered §7 on 2026-11-11 at 03:52:52 UTC ("Go with your picks"); the answers are recorded in §7 and applied in the sections they change.
- **Plan items:** C0 and C0b of `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` (rows at lines 64 and 65).
- **Tree:** every `file:line` below was read at `c314fd4` on branch `claude/ws17-freeze-sha-20261111`. That is `5777e98` plus docs-only commits, so code lines match the freeze SHA.
- **Who builds from this:** Sonnet writes the Python message types and tests. Kimi builds C3, C7-py, C7b, C4 and C5. Codex builds C2, C6 and C7a and reviews.
- **Words:** "must" is a rule a reviewer can fail a PR on. "Untested" means nobody has run it; the test that would settle it is named beside it.

## 0. Findings that change the brief

Read these first. They come from the code and they change what C3, C7-py and C7a build.

1. **The `actions` table gate is retired.** `prepare_commit`, `commit`, `prepare_push` and `push` all return `sandbox_required()` (`mcp_servers/mcp_git/logic.py:241-258`). So do `repo_write_file` and `repo_commit_write` (`mcp_servers/mcp_repo/logic.py:468-475`). Migration 0026 expired every pending row and its comment says nothing creates an action any more (`jarvis/db.py:660-674`).
2. **`hasPendingDraft` cannot be true against a current bot.** It is true only when the newest drawer result came from `prepare_commit`, `prepare_push` or `repo_write_file` (`macos/MortimerHost/Sources/MortimerHost/Stores/DisplayResultStore.swift:29-33`). Those tools now return `{"ok": false, ...}` (`mcp_servers/development_boundary.py:21-26`), and `build_display_payload` returns `None` for `ok is False` (`jarvis/bot/display.py:146-147`). This is derived from the code and untested live. Test: feed `sandbox_required()` as the result of `prepare_commit` to `build_display_payload` and expect `None`.
3. **The live confirmation gate is the two-phase tool call.** A tool called with `confirm=false` returns a preview. The same tool called with `confirm=true` acts. Previews carry `needs_confirmation: true` (`mcp_servers/mcp_selfedit/logic.py:257`, `:729`, `:904`, `:938`; `mcp_servers/mcp_web/logic.py:604`, `:692`; `mcp_servers/mcp_apps/logic.py:315`) or `pending: true` (`mcp_servers/mcp_apps/logic.py:196`). The Supervisor's rule 9 sends the user's yes back to the same specialist (`jarvis/prompts.py:71`). Section 3 builds on this gate, not on the `actions` table.
4. **The client gets no approval signal today.** None of the previewing tools except `app_create` is in `DISPLAY_TOOLS` (`jarvis/bot/display.py:27-62`), and `app_create` is not in `draftTools`. So the needs-you ring, the drawer dot and the top bar signal (`OrbFieldView.swift:289`, `DrawerView.swift:140-141`, `TopBarView.swift:203`) have no live source. Section 3 adds one.
5. **A second approval path exists and works: the file-send offer.** The bot sends `input/offer`; a spoken yes or no becomes `input/consent` (`jarvis/bot/pipeline.py:2266-2292`); the app shows "Approval required" with a button (`macos/MortimerHost/Sources/MortimerHost/Console/AttachmentTrayView.swift:28-36`). Section 3 leaves it as it is.

## 1. Composed answer layout

### 1.1 Where the layout rides

The layout is one new optional field, `layout`, on the existing display payload. The message stays `{"type": "display", "display": {...}}` (`jarvis/bot/pipeline.py:1052`). This is what the mockup asks for: "A versioned `layout` field on DisplayPayload, decoded leniently" (`docs/interface-research/orb-plasma/mortimer-ui-directions.html:385`).

Reasons:

- An old client ignores unknown keys. `DisplayPayload` decodes only the keys it declares (`macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:308-320`, comment at `:335-337`). It keeps rendering `title` and `body`.
- An old payload has no `layout`. A new client renders it through the existing typed views, as today (`macos/MortimerHost/Sources/MortimerHost/Display/DisplayContentView.swift:28-75`).
- Every emitter already goes through one envelope path, `_prepare_app_message`, which stamps `origin_request_id` (`jarvis/bot/pipeline.py:2060-2071`). The composer needs that id and gets it for free.

A new message type was rejected. An old client turns an unknown type into `.unknown` and drops it (`AppMessage.swift:578`, `AppMessageRouter.swift:459-467`), so the answer would vanish instead of degrading.

### 1.2 Envelope fields added to the display payload

| Field | Type | Rule |
|---|---|---|
| `answer_id` | string, UUID | Identity of the composed answer. Stable across updates. One per request (1.5). |
| `layout` | object | The block kit below. Absent on protected payloads (1.9). |

All existing fields stay and keep their meaning. The composer must still fill `kind`, `title`, `body`, `images`, `basemap_images`, `links`, `agent`, `run_id`, `ts`, `surface` and `tool` (`jarvis/bot/display.py:165-183`), because they are the fallback for old clients and for layout failures.

### 1.3 The `layout` object

```json
{
  "version": 1,
  "revision": 2,
  "template": "brief_and_weather",
  "title": "This morning and tomorrow",
  "summary": "Six new messages, two worth a look. Rain is likely tomorrow after 2 PM.",
  "complete": true,
  "blocks": [
    {"id": "b1", "type": "header", "title": "This morning and tomorrow",
     "summary": "Six new messages, two worth a look. Rain is likely tomorrow after 2 PM.",
     "agents": [{"name": "Librarian", "latency_ms": 600}, {"name": "Analyst", "latency_ms": 2400}]},
    {"id": "b2", "type": "stats", "items": [
      {"value": "6", "label": "new messages"},
      {"value": "2", "label": "flagged", "tone": "approval"},
      {"value": "70%", "label": "rain tomorrow, peak 2 PM"},
      {"value": "64° / 51°", "label": "high / low"}]},
    {"id": "b3", "type": "list", "title": "Inbox · since 6 PM yesterday",
     "items": [{"title": "Dana Reyes", "detail": "Contract redlines", "meta": "7:12 AM", "tone": "approval"}],
     "more_count": 1, "source": {"tool": "daily_brief", "run_id": "4f1c0a2e"}},
    {"id": "b4", "type": "chart", "title": "Rain chance tomorrow", "chart": "bar", "unit": "%",
     "points": [{"label": "12 PM", "value": 40}, {"label": "2 PM", "value": 70, "highlight": true}],
     "a11y": "Rain chance peaks at 70 percent at 2 PM."},
    {"id": "b5", "type": "weather", "weather": {"schema": "..."},
     "source": {"tool": "weather_report", "run_id": "9b7d11c3"}},
    {"id": "b6", "type": "sources", "items": [{"label": "weather.gov", "url": "https://www.weather.gov/"}]},
    {"id": "b7", "type": "actions", "items": [
      {"id": "a1", "label": "Hourly detail", "kind": "ask", "text": "Show the hourly detail for tomorrow."},
      {"id": "a2", "label": "Send to second screen", "kind": "console", "action": "display_show"}]}
  ]
}
```

The sample content follows the mockup at `mortimer-ui-directions.html:310-392`. The `weather` object above is abbreviated; it is the existing weather view.

Layout fields:

| Field | Type | Rule |
|---|---|---|
| `version` | int | `1`. See 1.8. |
| `revision` | int ≥ 1 | Rises by one each time the same `answer_id` is sent again. A client ignores a revision not higher than the one it holds. |
| `template` | string ≤ 40 | Name of the fixed template that built it (1.6). For logs and tests only. |
| `title` | string ≤ 120 | Card title. Also VoiceOver's name for the card. |
| `summary` | string ≤ 600 | One or two sentences. Plain text. |
| `complete` | bool | `false` while more results for the request may still join. `true` when the request's work is done. |
| `blocks` | array, 1 to 24 | In display order. |

### 1.4 Block types

Every block has `id` (string ≤ 40, unique inside the layout, stable across revisions) and `type`. Every block may carry:

- `a11y`: string ≤ 300. The VoiceOver summary. Required on `chart` and `media`.
- `source`: `{"tool": str ≤ 80, "run_id": str ≤ 120, "agent": str ≤ 80}`. Provenance only, never content identity. Same rule as `runID` today (`AppMessage.swift:265-267`).

`tone` is one of `neutral` (default), `ok`, `approval`, `error`. They map to the C0b tokens (section 5). A tone must never be the only cue; the label carries the meaning.

**Content blocks (new views in C4):**

| `type` | Fields | Limits |
|---|---|---|
| `header` | `title`, `summary`, `agents: [{name, latency_ms}]` | title ≤ 120; summary ≤ 600; ≤ 6 agents. At most one, and it must be first. |
| `stats` | `items: [{value, label, tone?}]` | 1 to 4 items; value ≤ 16; label ≤ 60 |
| `list` | `title?`, `items: [{title, detail?, meta?, tone?}]`, `more_count?` | ≤ 12 items; title ≤ 120; detail ≤ 240; meta ≤ 40; `more_count` ≥ 0 |
| `chart` | `title?`, `chart` (`"bar"` only in v1), `unit?`, `points: [{label, value, highlight?}]`, `a11y` | 2 to 48 points; label ≤ 16; value a finite number |
| `text` | `format` (`"markdown"` or `"plain"`), `text` | ≤ 30,000 chars, the existing `DOC_DISPLAY_MAX_CHARS` (`jarvis/bot/display.py:106`) |
| `media` | `images: [url]`, `basemap_images?: [url]`, `caption?`, `a11y` | ≤ 9 images each (the radar grid is 3 by 3); caption ≤ 240 |
| `sources` | `items: [{label, url?}]` | ≤ 12 items; label ≤ 120; url ≤ 2,048 |
| `actions` | `items: [{id, label, kind, ...}]` | ≤ 4 items; label ≤ 40. See below. |

**Wrapper blocks (C4 wraps the existing typed views):**

| `type` | Field | Existing view | Existing decode |
|---|---|---|---|
| `weather` | `weather` | `Display/WeatherCardView.swift` | `WeatherCard`, lenient (`AppMessage.swift:286-289`) |
| `brief` | `brief` | `Display/BriefCardView.swift` | `BriefCard`, lenient (`AppMessage.swift:290-293`) |
| `roadmap` | `roadmap`, `roadmap_timezone` | `Display/RoadmapView.swift` | `RoadmapSnapshot`, valid or dropped (`AppMessage.swift:352-353`) |
| `commands` | `commands`, `note`, `expect_output` | `commandsBlock` (`DisplayContentView.swift:130`) | `AppMessage.swift:275-277` |
| `graph` | `image_url`, `summary` | `Display/GraphImageView.swift` | built from `images[0]` today (`display.py:496-507`) |

`actions` items. `kind` is closed:

- `"ask"`: `text` ≤ 400. A tap sends it as a typed request (section 2) with `source: "chip"`. The composer writes the text from a template. A model never writes it.
- `"console"`: `action`, plus optional `target` and `args`. `action` must be in `ALLOWED_ACTIONS` (`jarvis/bot/console_protocol.py:11-33`) and the app runs it through `ConsoleActionCoordinator`, the same path its own buttons use. No new action is added by this contract.

An `actions` block must never hold approve or decline. Approvals do not ride the carousel (`mortimer-ui-directions.html:454`); they are section 3.

Copy, Share and Export are not blocks. They sit behind the card's "…" menu (`mortimer-ui-directions.html:384`) and keep their current protected-content checks.

### 1.5 How results join into one answer

**The join key is `origin_request_id`.** The bot stamps it on every display payload sent during a foreground request (`jarvis/bot/pipeline.py:2063-2069`). `run_id` is the tie-break inside a request and is never the key, because one request can run several delegations.

Rules for the composer (C3, `jarvis/bot/compose*.py`):

1. One instance per connection, like `WeatherReportMerger` (`jarvis/bot/display.py:531-547`). State is keyed by `origin_request_id`.
2. The first result for a request creates `answer_id` and sends revision 1 with `complete: false`.
3. Each later result for the same request is added to the same answer. The composer sends the whole layout again with `revision + 1`. It never sends a delta.
4. The answer is `complete: true` when the request has no delegation in flight and no weather half pending. The existing flush point is `delegate_done` (`jarvis/bot/pipeline.py:1066-1079`).
5. A result with no `origin_request_id` (a watcher's late plan or research report, a late delegation result) is its own answer with its own `answer_id`. It never joins another request's answer. This matches box 193: background arrivals join the carousel unread (`docs/acceptance/mac-acceptance-2026-11-11.md:84`).
6. Never suppress a real result. A lone half still renders, as `WeatherReportMerger` already guarantees (`display.py:405-413`, `:611-618`).
7. Hold at most 8 open answers per connection and drop the oldest open one to `complete: true` first. Barge-in survival can run more than one delegation at once (`display.py:537-539`).
8. `WeatherReportMerger` stays. It still pairs `get_weather` with `get_weather_radar` per run and subject. The composer takes its merged `weather_report` payload as one input. One implementation of that pairing, not two.
9. The legacy fields on a composed payload are built from the whole answer: `title` is `layout.title`, `body` is the blocks rendered as markdown in order, `kind` is `"markdown"`. Exception: when the answer holds exactly one typed result, keep that result's own `kind` and its top-level `weather`, `brief` or `roadmap`, so an old client shows the typed card.

Client rule (C4, C5): a payload whose `answer_id` matches a held card replaces that card in place when its `revision` is higher. Card identity, pin state and position do not change. An old client has no `answer_id` and shows each revision as a new card. That is the accepted degrade.

### 1.6 Layouts are built by code from fixed templates

A model never chooses blocks. The mockup's risk note says model-chosen layouts wobble and to start with fixed templates per result kind (`mortimer-ui-directions.html:386`). This also matches the repo's rule that code assembles structure (`WeatherReportMerger`, `display.py:531-547`).

v1 templates, one per row of the mapping in 1.7, plus `joined` for an answer with two or more results. `joined` is: one `header`, an optional `stats` row drawn from the results that offer stats, then each result's own blocks in arrival order, then one merged `sources` block, then one `actions` block.

### 1.7 Mapping from today's display payloads

Tools are from `DISPLAY_TOOLS` (`display.py:27-62`). Surfaces are from `DISPLAY_SURFACE` (`display.py:68-97`). `surface` keeps its meaning and its default (`display.py:98`, `AppMessage.swift:338-339`).

| Emitter (tool) | Formatter | Surface | Template | Blocks |
|---|---|---|---|---|
| `web_search` | `display.py:230-246` | window | `research` | header; text (answer and snippets); sources (from `links`) |
| `get_weather` alone | `display.py:270-280` | window | `weather` | header; text (the `human` line and daily table) |
| `get_weather_radar` alone | `display.py:283-297` | window | `radar` | header; media (tiles and basemap) |
| `weather_report` (merger, `local_weather`) | `display.py:405-455`; view at `:188-194` | window | `weather` | header; weather (wrapper) when `weather_view` returns a view, else text plus media |
| `app_create` | `display.py:300-314` | drawer | `app` | header; text; list of files; sources (repo link) |
| `app_write_file` | `display.py:317-330` | drawer | `code` | header; text |
| `git_diff_summary` | `display.py:333-341` | drawer | `code` | header; text |
| `prepare_commit`, `prepare_push`, `commit`, `push`, `repo_write_file` | `display.py:344-377` | drawer | none | These tools are retired (section 0). Keep the formatters. No template is needed. |
| `repo_read_file` | `display.py:380-387` | window | `document` | header; text |
| `repo_read_file` of `ROADMAP.md` | `display.py:206-222` | window | `roadmap` | header; roadmap (wrapper) |
| roadmap unavailable | `display.py:138-144` | window | `notice` | header; text |
| `plan_ready` | `display.py:390-402` | window | `document` | header; text. See the note below. |
| `research_report` | `display.py:458-493` | window | `document` | header; text; list "Crawl issues" for failed sites |
| `memory_graph_view`, `graph_view` | `display.py:496-507` | window | `graph` | header; graph (wrapper) |
| `show_commands` | `jarvis/bot/handoff_tools.py:277-289` | window | `commands` | header; commands (wrapper) |
| `daily_brief` (mail brief) | `jarvis/bot/brief_tool.py:199` | per that tool | `brief` | header; brief (wrapper) |
| `shared_content` analysis | `jarvis/bot/pipeline.py:2851-2858` | drawer | `analysis` | header; text. See the note below. |
| `read_clipboard` | `jarvis/bot/handoff_tools.py:346-354` | window | not composed | Stays a legacy payload with no `layout` (1.9). |
| `protected_result` | `jarvis/bot/pipeline.py:1118-1134` | window | not composed | Stays a legacy payload with no `layout` (1.9). |

Notes:

- `_fmt_plan_ready` returns its footer in the `images` slot (`display.py:401-402`: `footer` is the fourth tuple element). The `document` template must put "saved to …" in the text block and must not emit a `media` block from it. Whether today's client shows a broken image for it is untested. Test: decode a `plan_ready` payload with a `saved_path` and render it.
- The `shared_content` payload sends its answer in a `text` key with `kind: "text"` (`pipeline.py:2852-2856`). `DisplayPayload` declares no `text` key (`AppMessage.swift:308-320`). Whether that answer renders today is untested. Test: decode that payload in `AppMessageTests` and check `body`. The `analysis` template must put the answer in a `text` block and also in `body`.
- Emit sites the composer must cover are the ones the plan lists for C3: `pipeline.py:1052` and `:1077` (agent events), `:1120` (protected, not composed), `:1323` (weather card), `:1374` (brief), `:1560` (direct tools), `:2545` and `:2568` (plan and research watchers), `:2851` (shared content).

Swift readers that change:

- `AppMessage.swift:244-365`: add `answerID` and `layout`, both lenient (`try?`), like `weather` at `:349`.
- `DisplayResultStore.swift:35-41`: `apply` replaces by `answer_id` when present.
- `AppMessageRouter.swift:299-440`: the display branch treats a known `answer_id` as an in-place update, the way it already treats a known roadmap or weather subject (`:300-317`).
- `Display/DisplayContentView.swift:28-75`: when `layout` is valid, render blocks. Otherwise the current branches.
- `Display/WorkspaceResultDetails.swift:6`: the fixed Summary, Sources and Connections modes are replaced by the block renderer (`mortimer-ui-directions.html:384`).

### 1.8 Versioning

- `layout.version` is an integer. v1 is this document.
- A client that reads `version` higher than it knows, or fails to decode `layout`, must ignore `layout` and render the legacy fields. It must not show an error.
- A client that meets an unknown block `type` skips that block. If no block is left, it renders the legacy fields.
- A client ignores unknown fields inside a known block.
- Adding a block type or an optional field does not raise `version`. Changing the meaning or type of an existing field does.
- The bot must always send the legacy fields. That is the whole compatibility story for old clients.
- An old payload (no `layout`) renders as today. Fixtures: keep `macos/JarvisKit/Tests/JarvisKitTests/Fixtures/display_window.json` unchanged and add new ones beside it.

### 1.9 What never goes in a layout

1. **Nothing from a sensitive turn.** The composer calls `is_sensitive()` (`jarvis/bot/sensitive_turn.py:79-93`) when it builds or updates an answer. If it returns true, the payload is sent with no `layout` and no `answer_id`, and it never joins an open answer. `is_sensitive()` is fail-closed: an unset context reads as sensitive (`sensitive_turn.py:91-92`). Keep that. Do not add a second check.
2. **No protected result.** On a protected route the event callback is stripped to seven metadata keys (`jarvis/agents/base.py:324-335`, used at `:935`), so the composer never sees the result. The result itself goes to the app through the awaited private sink with a `data_policy` (`jarvis/bot/pipeline.py:1109-1137`). That payload keeps its legacy shape. The client rule: if `isProtectedLocal` is true (`AppMessage.swift:303-306`), ignore any `layout`.
3. **No clipboard text.** `read_clipboard` content must never be persisted (`AppMessage.swift:278-279`; `handoff_tools.py:344-345`). Composed answers can be kept in Output history and recents, so clipboard text stays out of them.
4. **No secrets.** No environment values, key names with values, tokens, or vault content. The composer reads only the fields the legacy formatter for that tool already displays. It never reads `os.environ` or `jarvis.vault`.
5. **URLs.** `https` or `http` only. No user-info part. No `file:`, `data:` or `javascript:`. Sidecar image URLs for graphs are the one loopback exception and stay as they are today.
6. **No model-written structure.** Text from a model may appear inside `text`, `summary`, list and stat strings. Block types, `actions` and URLs come from code.
7. **No approval controls** (section 3).

### 1.10 Size limits

| What | Limit | Basis |
|---|---|---|
| Whole `display` message, compact UTF-8 | 1,200 KiB | The existing ceiling for a display payload (`pipeline.py:502`; Swift at `ConsoleActionCoordinator.swift:76`). The WebSocket accepts 4 MiB (`NativeAudioTransport.swift:683`). |
| `layout` without wrapper data | 256 KiB | New. |
| Blocks | 24 | New. |
| One `text` block | 30,000 chars | `display.py:106` |
| A roadmap wrapper | 1 MiB | `display.py:214`; `AppMessage.swift:235` |

Over a limit, the composer drops blocks from the end until it fits, sets a last `text` block "More results were left out to fit.", and logs one line. If it still does not fit, it sends the legacy payload with no `layout`. It never truncates inside a wrapper's data.

### 1.11 How answers sit in the carousel

- One card per `answer_id`. A legacy payload with no `answer_id` is one card each, as now.
- Placement A (the open area beside the thread) is where answers land. Placement B is the "show all results" overlay and shows the same set (`mortimer-ui-directions.html:459-463`; box 195 at `mac-acceptance-2026-11-11.md:86`).
- In A the card is one column (`mortimer-ui-directions.html:463`). Blocks stack in array order. The renderer must not reorder them.
- The front card shows all blocks. Neighbours show `layout.title` sharp and the body blurred (`mortimer-ui-directions.html:455`).
- The carousel stops at both ends. It does not loop (`macos/MortimerHost/Sources/MortimerHost/Stores/WorkspaceStore.swift:509-516`).
- It holds pinned cards plus the recent 10 (`Stores/WorkspaceRecents.swift:16`). Output history keeps 20 (`App/AppTuning.swift:44`).
- A revision of the front card must not move focus or scroll position. A revision of a non-front card sets its "updated" marker (box 194).
- Ordinary speech creates no card (box 192). The composer sends nothing for a turn with no display-worthy result.
- The second screen keeps its grid (plan decision 4, `MORTIMER_RELEASE_CLOSURE_PLAN.md:142`). It renders the same payloads through the same block renderer.
- VoiceOver reads one list: "Results, 2 of 5, <layout.title>", with only the front card exposed (`mortimer-ui-directions.html:455`).

### 1.12 Files

- Python: `jarvis/bot/display.py`, `jarvis/bot/compose*.py` (new), the emit sites in `jarvis/bot/pipeline.py` listed in 1.7, `handoff_tools.py`, `weather_tool.py`, `plan_watcher.py`, `research_watcher.py`. Tests: `tests/unit/test_display.py` (exists), `tests/unit/test_compose.py` (new).
- Swift: `Display/**`, `App/AppMessageRouter.swift`, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`, `macos/JarvisKit/Tests/JarvisKitTests/Fixtures/`, `Stores/DisplayResultStore.swift`.

## 2. Typed request

### 2.1 How client messages reach the bot today

- The app sends raw JSON, no envelope (`macos/JarvisKit/Sources/JarvisKit/ClientMessage.swift:3-5`, `:28-48`), through `JarvisClient.send` (`JarvisClient.swift:359-362`).
- On the WebSocket, `ClientMessageProcessor` hands every `InputTransportMessageFrame` to each bound handler (`jarvis/bot/ws_transport.py:119-142`). On WebRTC the same handlers run from the connection's `app-message` event (`jarvis/bot/pipeline.py:2884-2892`). Both lists are bound in one place (`pipeline.py:2884-2900`).
- Each handler unwraps with `_unwrap_client_message` and returns unless `type` is its own (`pipeline.py:2038-2057`, example at `:2598-2601`).
- Versioned messages carry `session_id` and `generation` and are checked against the session (`jarvis/bot/console_protocol.py:320-343`).

### 2.2 Message: `turn/typed` (client to bot)

```json
{
  "type": "turn/typed",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "request_id": "00000000-0000-4000-8000-000000000003",
  "text": "What came in overnight, and will it rain tomorrow?",
  "source": "composer"
}
```

The type must not start with `input/`. `handle_shared_content` claims every type with that prefix (`pipeline.py:2840-2841`).

Validation (a pure function in `jarvis/bot/typed_request.py`, same style as `validate_ready`):

1. The message is an object with exactly these seven keys. Any other key is rejected.
2. `type == "turn/typed"` and `version == 1` (an int, not a bool).
3. `session_id` and `generation` parse as UUIDs and equal the session's. Compare as UUIDs, not strings, because Foundation sends uppercase hex (`pipeline.py:2680-2684`).
4. `request_id` parses as a UUID.
5. `text` is a string. After trimming it has 1 to 4,000 Unicode scalars. It has no control characters except newline and tab. Count scalars on both sides, as `ConsoleActionRegistry.swift:59-62` does.
6. `source` is `"composer"` or `"chip"`.
7. The compact UTF-8 message is at most `MAX_MESSAGE`, 32 KiB (`console_protocol.py:10`).

A message that fails rule 1 to 4 gets no reply, because it has no trustworthy identity. That is how `ConsoleSession.accept` treats malformed requests (`jarvis/bot/console_session.py:71-75`). Log one content-free line.

### 2.3 Message: `turn/result` (bot to client)

```json
{
  "type": "turn/result",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "request_id": "00000000-0000-4000-8000-000000000003",
  "status": "accepted",
  "code": "accepted"
}
```

`status` is `accepted` or `rejected`. `code` is one of `accepted`, `duplicate`, `invalid_text`, `stale_session`, `not_ready`, `disabled`. The reply never echoes the text.

A repeated `request_id` returns the first reply again and starts no second turn. Keep at most 128 replies for 300 seconds, the same bounds as `ConsoleSession` (`console_session.py:31-32`).

### 2.4 What the bot must do with an accepted request

These are behaviours C7-py must test. The mechanism is C7-py's choice. The plan records that reusing the context-injection path as a real user turn is not tested (`MORTIMER_RELEASE_CLOSURE_PLAN.md:158`), so each rule below is untested until its unit test exists.

1. **It is a user turn.** The text enters the LLM context as a `role: "user"` message and starts exactly one model run. It is not a `[system]` note. `inject_context` is the existing channel for adding a user message and pushing a context frame (`pipeline.py:2444-2447`).
2. **Sensitivity is checked first.** Call `arm_from_text(text)` before anything is logged or stored, as the spoken path does (`jarvis/bot/transcript_log.py:160`). A typed turn starts a new turn, so clear the previous turn's flag first, as `UserStartedSpeakingFrame` does (`transcript_log.py:138-143`).
3. **The transcript is written once.** Store the text in the conversations table as role `user`, unless the turn is sensitive (`transcript_log.py:161-163`, `:196-201`). On a sensitive turn the log line carries no text.
4. **It gets a foreground request.** Display payloads for this turn must carry an `origin_request_id` (`pipeline.py:2063-2069`) and the app must receive `console/turn` (`pipeline.py:311-316`), or the composer cannot join its results and the answer cannot come to the front (box 193). `ForegroundRequests` binds only to a `TranscriptionFrame` from the input source today (`pipeline.py:350-361`). How a typed turn gets its binding is the open mechanism. Test: a typed request followed by a display-worthy tool result yields a payload with a non-null `origin_request_id`.
5. **No voice consent parsing.** Typed text is never passed to `handle_voice_consent` (`pipeline.py:2266-2292`). A file-send offer is answered by its own controls.
6. **No speaker gate.** There is no audio to score. `TranscriptGate` is not involved.
7. **It interrupts speech.** If Mortimer is speaking, the typed request ends that speech as a spoken barge-in would. In-flight delegations survive, as they do for barge-in (`CLAUDE.md`, "Barge-in survival"). Untested. Test: a typed request during TTS leaves a running delegation's run row to finish.
8. **Refuse when the session is ending.** If `runtime.alive` is false, reply `not_ready` and start nothing (`pipeline.py:2452-2453`).
9. **No echo.** The bot must not send a `user-transcription` frame for a typed turn. The app adds the user's line itself (2.5). Test: record the frames sent for a typed turn and assert none has that type. If the chosen mechanism cannot avoid the frame, change 2.5 to "the app waits for the bot's frame" in this document before C7b lands. One or the other, never both.
10. **Kill switch.** `JARVIS_TYPED_REQUEST_ENABLED`, default on, read once at registration. Off: the handler replies `disabled`.
11. **A bare yes follows 3.10.** Typed text that is a bare yes is handled exactly as a spoken one (§3.10). It never approves when more than one approval is open.

### 2.5 What the app must do

- Add `case typedRequest(TypedRequest)` to `ClientMessage` (`ClientMessage.swift:6-19`). It is a closed enum so no caller invents a type.
- Send only when `client.consoleSessionID` and `consoleGeneration` are set. They come from `console/hello` (`AppMessageRouter.swift:143-148`), which the bot sends only when `JARVIS_COMMAND_CONSOLE_ENABLED` is true (`pipeline.py:2409-2414`). Larry's answer to §7 question 5: on `next` this flag defaults to **on**. Today it is read in four places with two different defaults: false at `pipeline.py:1401` and `:2643` and in `jarvis/config.py:184` (bridged at `:369-371`), but on unless explicitly false at `pipeline.py:2764`. C7-py must make all four agree on the new default through one helper, and keep `false` as the kill switch. With no hello, the composer field is disabled and says why.
- On `accepted`, append the text to `ConversationStore` as one user entry. On `rejected`, keep the text in the composer and show the reason. Never both.
- A `chip` request comes from an `actions` block of kind `ask` (1.4). It uses the same message.
- ⌘K focuses the composer. It sends nothing by itself.
- Files and images do not use this message. They keep the `input/*` transfer (`ClientMessage.swift:13-17`).

### 2.6 Files

- Python: `jarvis/bot/typed_request.py` (new: types, validation, handler), registration lines in `jarvis/bot/pipeline.py` (both handler lists, `:2884-2900`). Tests: `tests/unit/test_typed_request.py` (new), a fixture `tests/fixtures/typed_request/turn_typed.json` (new).
- Swift: `macos/JarvisKit/Sources/JarvisKit/ClientMessage.swift`, `JarvisClient.swift`, `AppMessage.swift` (decode `turn/result`), `ClientMessageTests`, `Console/AttachmentTrayView.swift`, `MortimerHostApp.swift` or `ConsoleView.swift` for ⌘K.

## 3. Approve and decline

### 3.1 Recommendation

**Make it a client message pair (`approval/decide`, answered by `approval/result`), fed by a bot-owned pending list (`approval/pending`, `approval/settled`). Do not make it a console action.**

Reasons, from the code:

1. **Wrong direction and wrong owner.** A console request is how voice drives state the app owns. The bot sends it and the app answers (`pipeline.py:1427-1437`; `AppMessageRouter.swift:149-153`). In the other direction the bot answers "unsupported" to everything except `help` and a roadmap refresh (`pipeline.py:2806-2812`). A pending approval is state the bot owns.
2. **A console action is something the model can send.** `console_action` is a Supervisor tool (`jarvis/bot/console_actions.py:28-31`, built at `pipeline.py:1527`) and the hello advertises every entry of `ALLOWED_ACTIONS` (`pipeline.py:2413`). An `approve` entry there would put approval in the model's hands. Rule 9 says the Supervisor never confirms on a specialist's behalf (`jarvis/prompts.py:71`). Whether the tool's enum is exactly `ALLOWED_ACTIONS` is untested here. Test: read the enum in `CONSOLE_ACTION_SCHEMA`.
3. **The action table is full.** `ALLOWED_ACTIONS` has 99 entries (counted with `ast` at this tree). `hello()` cuts the list at 100 (`console_protocol.py:309`) and `validate_ready` rejects more than 100 (`:334`). Two new actions make 101, so one existing action would drop out of the hello without an error.
4. **There is a precedent for a dedicated consent message.** The file-send approval already has its own versioned type with session, generation, request id and a boolean (`pipeline.py:2283-2291`; `macos/JarvisKit/Sources/JarvisKit/SharedContentTransfer.swift:107-122`).
5. **Less to change.** A console action touches `console_protocol.py`, the protocol fixture, `ConsoleProtocol.swift` (`:5-46`) and `ConsoleActionRegistry.swift`. The client message touches none of them, so C7a's conditional files drop out of its list.

### 3.2 The gate it reuses

The gate is the tool's own two-phase call (section 0, item 3). The approval message never calls a tool. An approve tap is delivered to the Supervisor as the user's own turn, and rule 9 then sends the confirmation to the specialist that made the preview. That is the same path a spoken "yes" takes.

Hard rules:

1. The approval handler must never call `SkillRegistry.call`, an MCP tool, or the admin sidecar. A unit test greps `jarvis/bot/typed_request.py` for those names, in the style of `test_module_imports_nothing_that_executes`.
2. The text of the injected turn is built by the bot from a fixed template in `jarvis/prompts.py` and from what the bot recorded. The client sends an id and an enum. No client string reaches the model through this message.
3. Each `approval_id` is single use.
4. A decision for an unknown, expired or settled approval does nothing and says so.
5. On a sensitive turn no approval is published and no decision is accepted. The user answers by voice.
6. Decline never runs anything.
7. A bare yes approves only when exactly one approval is open (§3.10).

### 3.3 The pending list (bot)

The bot records a pending approval when a sub-agent tool result is a JSON object with `pending: true` or `needs_confirmation: true` at the top level. The event that carries it is `agent_tool_result` in `on_agent_event` (`pipeline.py:971-981`). Note that the sub-agent loop's own draft check reads only `pending` (`jarvis/agents/base.py:338-345`); this list reads both flags.

For each one it stores, in memory, for this connection only:

- `approval_id` (new UUID), `agent`, `tool`, `run_id`, `origin_request_id`
- `summary`: the result's `summary` string, cut to 600 chars
- `ref`: the first present of `staging_id`, `preview_id`, `draft_id`, `action_id` in the result, as `{"kind": ..., "value": ...}`. Value ≤ 120 chars. May be absent. `app_create` and the research previews carry none (`mcp_apps/logic.py:193-205`, `mcp_web/logic.py:600-606`).
- `expires_at`: now plus 600 seconds, the self-edit staging lifetime (`jarvis/admin/server.py:412`)

It settles an entry when:

- a decision is accepted (`approved` or `declined`);
- a later result from the same `agent` and `tool` arrives that is not a preview (`resolved`: the user said yes by voice and the tool ran);
- a newer preview from the same `agent` and `tool` arrives (`superseded`);
- the time runs out (`expired`);
- the session ends (no message; the app clears its list on disconnect).

At most 8 open entries. A ninth settles the oldest as `superseded`.

On a protected route the callback carries no result (`base.py:324-335`), so nothing is recorded. That is rule 5 holding by construction.

Self-edit is not paused by this. Rule 9 lets the developer confirm a self-edit in the same turn after speaking the preview (`prompts.py:71`). Its preview is published and then settled as `resolved` a moment later. The app must tolerate a pending item that settles before it is drawn.

### 3.4 Message: `approval/pending` (bot to client)

```json
{
  "type": "approval/pending",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "approval_id": "00000000-0000-4000-8000-000000000010",
  "origin_request_id": "00000000-0000-4000-8000-000000000020",
  "run_id": "4f1c0a2e9b7d",
  "agent": "Developer",
  "tool": "plan_start",
  "summary": "Ready to draft a plan for the weather cache. Say yes to start.",
  "ts": 1794366120.0,
  "expires_at": 1794366720.0
}
```

Client validation: `version == 1`; session and generation match; `approval_id` is a UUID; `summary` is 1 to 600 chars; `agent` and `tool` ≤ 80; `expires_at > ts`. `origin_request_id` may be null. An invalid message is dropped.

### 3.5 Message: `approval/settled` (bot to client)

```json
{
  "type": "approval/settled",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "approval_id": "00000000-0000-4000-8000-000000000010",
  "state": "approved"
}
```

`state` is `approved`, `declined`, `resolved`, `superseded` or `expired`. The app removes the item. A settle for an unknown id is ignored.

### 3.6 Message: `approval/decide` (client to bot)

```json
{
  "type": "approval/decide",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "request_id": "00000000-0000-4000-8000-000000000030",
  "approval_id": "00000000-0000-4000-8000-000000000010",
  "decision": "approve"
}
```

Validation: exactly these seven keys; `version == 1`; session and generation match as UUIDs; `request_id` and `approval_id` are UUIDs; `decision` is `"approve"` or `"decline"`. Nothing else is accepted. There is no free-text field.

### 3.7 Message: `approval/result` (bot to client)

```json
{
  "type": "approval/result",
  "version": 1,
  "session_id": "00000000-0000-4000-8000-000000000001",
  "generation": "00000000-0000-4000-8000-000000000002",
  "request_id": "00000000-0000-4000-8000-000000000030",
  "approval_id": "00000000-0000-4000-8000-000000000010",
  "status": "accepted",
  "code": "accepted"
}
```

`code` is one of `accepted`, `duplicate`, `unknown_approval`, `expired`, `already_settled`, `protected_turn`, `stale_session`, `disabled`. A repeated `request_id` returns the first reply.

### 3.8 What the bot does on an accepted decision

1. Settle the entry and send `approval/settled`.
2. Build the turn text from a template in `jarvis/prompts.py`:
   - approve: `Confirmed. Go ahead with the pending {tool} from {agent}.` plus ` ({ref.kind} {ref.value})` when a ref exists.
   - decline: `Declined. Do not run the pending {tool} from {agent}.`
3. Deliver that text through the same path as an accepted typed request (2.4), with rules 1 to 4, 7 and 8 of that list. It is the user's turn, so it is stored in the transcript as theirs.

Whether the Supervisor then reliably delegates the confirmation with the ref is untested. Tests: a C7-py unit test that the injected text contains the recorded `staging_id` exactly; a routing-eval case that a turn of that shape is delegated to the same agent (`tests/evals/routing_eval.py`).

### 3.9 What the app does

- A new `ApprovalStore` holds open approvals by `approval_id`. It is cleared on disconnect.
- `hasPendingDraft` (`DisplayResultStore.swift:30-33`) becomes true when the approval store has an open item or a file-send offer is pending (`AttachmentTrayView.swift:28`). The three readers keep reading that one property (`OrbFieldView.swift:289`, `DrawerView.swift:140`, `TopBarView.swift:203`). C6 moves the orb reader to the `#FFD84A` ring (`ORB_SPEC.md:69`).
- The thread shows each open approval inline, under the request it belongs to (`origin_request_id`), with the summary and two buttons, "Approve" and "Decline". With a null `origin_request_id` it sits at the end of the thread.
- Approvals never appear on a carousel card (`mortimer-ui-directions.html:454`).
- Buttons disable after a tap until `approval/result` or `approval/settled` arrives. An `expired` or `superseded` item is removed with one line of text saying which.
- The buttons have text labels and VoiceOver labels that include the summary. The yellow token is never the only cue.
- When the bot asks which item a bare yes meant (§3.10), each open item's buttons stay in place; the question adds no new control.
- The file-send offer keeps its own protocol and its own buttons (`AttachmentTrayView.swift:28-36`). The thread may show it inline by calling the same `onApproveOffer` closure. It does not use `approval/decide`.

### 3.10 A bare yes with more than one approval open

Larry's answer to §7 question 1 (2026-11-11 03:52:52 UTC, "Go with your picks", choosing the coordinator's recommendation): a typed or spoken bare yes approves only when exactly one approval is open. With two or more open, Mortimer asks which, because approving the wrong one cannot be undone.

This is a code rule, not only a prompt rule:

1. **What counts as a bare yes.** A pure function `is_bare_yes(text)` in `jarvis/bot/typed_request.py`. After lowercasing, trimming, and removing trailing punctuation, the text is exactly one of a fixed list: `yes`, `yeah`, `yep`, `yup`, `sure`, `ok`, `okay`, `confirm`, `confirmed`, `approve`, `approved`, `go ahead`, `do it`, `yes please`. Anything longer or different is not bare ("yes, the plan one" is not bare and goes to the Supervisor as usual, which then has the words it needs).
2. **Zero or one open.** The turn goes to the Supervisor unchanged. Rule 9 handles it, as today.
3. **Two or more open.** The bot does not deliver the turn to the Supervisor. It speaks one fixed question built in code from a template in `jarvis/prompts.py` (`APPROVAL_WHICH_TEMPLATE`), naming each open item by agent and tool in pending order, for example "Two things are waiting: a plan from Developer and a comparison from Analyst. Which one?". It uses `TTSSpeakFrame`, with no model call, the way `ProgressWatcher` speaks. Nothing is approved and nothing settles. The user's next turn ("the plan", or a button tap) goes through the normal path.
4. **Where the check runs.** For typed text, in the `turn/typed` handler before 2.4's rule 1. For speech, on the final user transcript after `TranscriptGate` and before the context aggregator. The spoken check is a pipeline insertion in `jarvis/bot/pipeline.py` and is C7-py's. It must not run on a protected or sensitive turn, where no approval is open by rule 5 anyway.
5. **Logging.** One content-free line: `approval_yes_ambiguous open=<n> source=<typed|voice>`.

Untested until C7-py's tests exist: whether a spoken bare yes reaches the check as one final transcript, and whether holding it back leaves the context aggregator in a clean state. Tests: `is_bare_yes` cases both ways; with two open items, a bare yes produces the question and no context message; with one open, it passes through unchanged.

### 3.11 Files

- Python: `jarvis/bot/typed_request.py` (the approval types, the pending list and both handlers live beside the typed request, as the plan's C7-py row says), `jarvis/prompts.py` (three templates: approve, decline and `APPROVAL_WHICH_TEMPLATE`), registration lines, the `agent_tool_result` hook, the spoken bare-yes check (§3.10) and the `JARVIS_COMMAND_CONSOLE_ENABLED` helper (§2.5) in `jarvis/bot/pipeline.py`, and `jarvis/config.py:184` (that flag's default). Tests: `tests/unit/test_typed_request.py`, fixtures under `tests/fixtures/typed_request/`.
- Not touched: `jarvis/bot/console_protocol.py`, `tests/fixtures/command_console/protocol.json`, `ConsoleProtocol.swift`, `App/ConsoleActionRegistry.swift`.
- Swift: `ClientMessage.swift` (`case approvalDecide`), `AppMessage.swift` (decode the three bot messages), `Stores/ApprovalStore.swift` (new), `Stores/DisplayResultStore.swift`, `Console/ConversationThreadView.swift`, `App/AppMessageRouter.swift`, `Stores/ConversationStore.swift`.

## 4. Design rule from box 828

### 4.1 The rule

**There is one conversation surface: the thread. There is no compact rail. No other view shows live conversation text.**

"Live conversation text" means the user's and Mortimer's words from `ConversationStore.entries`, or from the transcription stream that fills it (`macos/JarvisKit/Sources/JarvisKit/JarvisClient.swift:588-600`).

- Exactly one view type reads `conversation.entries` to draw turns: `ConversationThreadView` (`Console/ConversationThreadView.swift:246`).
- The thread may be narrow, as in the carousel mockup's left column (`mortimer-ui-directions.html:393-450`). It is still the same view instance. A second, shorter rendering of the same turns is a violation.
- A composed answer's `summary` is result content, not conversation text. It may repeat what Mortimer said. It must come from the payload, never from the transcript.
- The orb shows state in a word ("Listening"). It shows no sentence.
- The activity row under a request names the current step. It is not a transcript line and never becomes a message (box 192, `mac-acceptance-2026-11-11.md:83`).

This replaces box 828 (`mac-acceptance-2026-11-11.md:75`). The original requirement is ROADMAP.md line 882, with its close condition at line 889.

### 4.2 What violates it today

These must be gone when C1a, C5 and C6 land:

- `Console/AdaptiveStageView.swift:91-92` draws `conversation.latestCaptions` through `ConversationStore.liveCaption`.
- `Console/OrbFieldView.swift:390`, `:396` and `:423` draw the last entries as captions.
- `Stores/ConversationStore.swift:30-32` defines `latestCaptions` and `liveCaption`. Delete both when their last reader goes.
- The `compactConversation` setting and its two toggles (`AdaptiveStageView.swift:19`, `:160-161`; `ConsoleActionBar.swift:27`, `:527-529`).

`Drawer/LogTab.swift:40` also reads `conversation.entries`. Larry's answer to §7 question 3: the Log tab stays, as history. It is the one other reader allowed; nothing else may draw conversation turns.

### 4.3 How a reviewer checks it

Run from the repo root. Each command must print only the allowed lines.

```bash
# 1. Who reads the transcript. Allowed: ConversationThreadView.swift and LogTab.swift (§7 question 3: the Log tab stays).
grep -rn "conversation\.entries\|\.latestCaptions\|liveCaption(" macos/MortimerHost/Sources --include=*.swift \
  | grep -v "Stores/ConversationStore.swift"

# 2. The compact rail is gone. Allowed: nothing.
grep -rn "compactConversation\|compactPresentation" macos/MortimerHost/Sources --include=*.swift

# 3. No other consumer of the transcription stream. Allowed: JarvisClient.swift and the request tracker
#    in ConversationThreadView.swift, which reads timestamps and ids, not text, for display.
grep -rn "user-transcription\|bot-llm-text" macos --include=*.swift
```

Then, on a build:

4. Speak one sentence and wait for the answer. Count the places where your words and Mortimer's words appear in the main window. The count is one each.
5. Open a result on the carousel and repeat. The count is still one each.
6. Open the second screen and repeat. The second screen shows no conversation text.
7. Send a typed request (section 2). Your line appears once.

Any PR that adds a view failing check 1 fails review, whatever else it does.

## 5. Tokens (C0b)

### 5.1 Colour tokens

Six new tokens in `AppTheme` (`macos/MortimerHost/Sources/MortimerHost/App/AppTheme.swift`). Values are the approved palette (`ORB_SPEC.md:15-22`; plan decision 2, `MORTIMER_RELEASE_CLOSURE_PLAN.md:140`).

| Token | Hex | RGB | Use | Contrast on `#15191D` |
|---|---|---|---|---|
| `AppTheme.listening` | `#6673FF` | 102, 115, 255 | Orb arcs while listening | 4.59:1 |
| `AppTheme.user` | `#2DD4BF` | 45, 212, 191 | Orb arcs and the thread marker for the user | 9.49:1 |
| `AppTheme.mortimer` | `#E07020` | 224, 112, 32 | Orb arcs and the thread marker for Mortimer. Reserved for Mortimer. | 5.47:1 |
| `AppTheme.ok` | `#A6FFC1` | 166, 255, 193 | Success marks | 14.89:1 |
| `AppTheme.approval` | `#FFD84A` | 255, 216, 74 | The needs-you ring, inline approvals, the `approval` tone | 12.76:1 |
| `AppTheme.error` | `#FF598B` | 255, 89, 139 | Errors, the `error` tone | 5.93:1 |

The contrast figures are the mockup page's calculations against the app background (`mortimer-ui-directions.html:544-556`). They are not measured on glass. C2 checks each token on glass.

Rules:

1. **Unchanged:** `amber` `#FFB454`, `green` `#3DDC97`, `red` `#FF5F56`, and `attn = amber` (`AppTheme.swift:23-27`). They keep their values and their meaning as general warning, success and failure.
2. `user` and `mortimer` must be the same values as `AudioPresentationTuning.userRGB` and `assistantRGB` (`App/AppTuning.swift:125-126`). One definition, referenced by the other. C2 picks which side owns it.
3. The doc comment at `AppTuning.swift:122` says `#FFB454` for Mortimer. The code says `#E07020`. C2 corrects the comment.
4. `listening` at 4.59:1 is for the orb and icons. Do not use it for text under 17 pt (`mortimer-ui-directions.html` palette note after line 556).
5. `mortimer` is never used for a warning, a button or a chart series. `approval` is never used for a general warning; that is still `amber`.
6. Layout tones map: `ok` to `AppTheme.ok`, `approval` to `AppTheme.approval`, `error` to `AppTheme.error`, `neutral` to `AppTheme.text`.
7. Moving call sites to the new tokens is C5 (cards) and C7a (thread), not C2.

Each new token also needs a Reduce Transparency and Increase Contrast check through the existing `Glass.swift` fallbacks. Untested until C2 runs it.

### 5.2 Orb-renderer-only constants

These are not theme tokens. They live in the orb renderer (`Console/CometOrbRenderer.swift`) and no other view may use them.

| Constant | Value | Use | Source |
|---|---|---|---|
| muted arc | `#5A6478` (90, 100, 120) | The one arc in the muted state | `ORB_SPEC.md:43`; state table at `mortimer-ui-directions.html:1140` |
| core | white, `rgba(255,255,255,0.95)` at the centre | The core in every active state | The core gradient near `mortimer-ui-directions.html:1199`; `ORB_SPEC.md` item 5 |

The idle colour in code is still `#7C8CFF` (`AppTuning.swift:127`). Changing it, and the two nucleus tests, needs Larry's OK (`ORB_SPEC.md`, "Gates and open items"). C0b does not change it.

### 5.3 Type tokens

The mockup page names three web font families (`mortimer-ui-directions.html:10`): Manrope for headings, Inter for body, JetBrains Mono for meta. The app bundles no custom font; a search of `macos/MortimerHost/Sources` for those names and for `.custom(` finds nothing. So the contract defines roles and sizes, on the system fonts. Larry's answer to §7 question 4: keep the system fonts. No font files are bundled.

| Token | Size / weight | Use | Mockup line |
|---|---|---|---|
| `answerHero` | 64 / ultralight (200) | The one big figure on a card | 279 |
| `stat` | 28 / light (300) | `stats` values | 333 |
| `answerTitle` | 17 / semibold | Card title, `header` title | 278 |
| `body` | 15 / regular | Thread text, `summary`, `text` blocks | 430 |
| `blockTitle` | 13 / semibold | Block titles | 340 |
| `chip` | 13 / medium | Chips | 73 |
| `detail` | 12 / regular | List detail, captions, source chips, action chips | 359, 365, 369 |
| `meta` | 11 / regular, monospaced | Provenance lines ("weather.gov · read 7:42 AM") | 288 |
| `label` | 11 / semibold, uppercase, tracking 0.18 em | State label beside the orb, section labels | 76 |

Sizes are points at the default text size. Whether they scale with the drawer's text-size setting (`sidecar_text`, `console_protocol.py:70`) is for C2 to state. Mockup pixels were not measured against the app's 15 pt thread text (`AdaptiveStageView.swift:93`), which matches `body`.

### 5.4 Files

`docs/contracts/**` only for C0b. C2 then edits `App/AppTheme.swift`, `App/Glass.swift`, `App/AppTuning.swift`, `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift`.

## 6. Test list for the Python types (Sonnet)

Pure functions, no pipecat imports, like `display.py` (`display.py:15-16`).

Layout (`tests/unit/test_compose.py`):
- every v1 template validates against 1.3 and 1.4 limits;
- two results with one `origin_request_id` give one `answer_id` and revisions 1 and 2;
- two results with different ids give two answers; a result with no id never joins;
- a sensitive turn gives no `layout` and no `answer_id`, and an unset context does the same;
- `protected_result` and `read_clipboard` payloads are returned unchanged;
- the legacy fields are always present;
- an oversized answer drops trailing blocks, then falls back to no `layout`;
- `plan_ready` with a `saved_path` yields no `media` block;
- a URL with user-info or a non-http scheme is dropped.

Typed request and approval (`tests/unit/test_typed_request.py`):
- the JSON examples in 2.2, 3.4, 3.5, 3.6 and 3.7 validate as written;
- each validation rule has one failing case; an extra key fails;
- uppercase UUIDs match;
- a duplicate `request_id` returns the first reply and starts nothing;
- text of 4,001 scalars fails; a control character fails;
- a preview result (`pending` or `needs_confirmation`) creates one pending item; a non-preview result from the same agent and tool settles it as `resolved`;
- approve on an expired or settled id is rejected and injects nothing;
- the injected text contains the recorded ref exactly and no client-supplied string;
- the handler module names no registry, MCP or sidecar call;
- `is_bare_yes` accepts each listed phrase (with case and trailing punctuation varied) and rejects "yes, the plan" and "yes and also";
- with two open approvals a bare yes yields the `APPROVAL_WHICH_TEMPLATE` question, injects no context message and settles nothing; with one open it passes through unchanged;
- the four `JARVIS_COMMAND_CONSOLE_ENABLED` reads agree: unset means on, `false` means off.

## 7. Decisions (answered by Larry)

Larry answered all five on 2026-11-11 at 03:52:52 UTC: "Go with your picks", choosing the coordinator's recommendations (which kept the draft's defaults for 2 to 5 and changed 1).

1. **Typed or spoken "yes" to an approval.** A bare yes approves only when exactly one approval is open. With two or more open, Mortimer asks which. This changes the draft, which had let a yes approve the newest item. Applied in §3.10, §3.2 rule 7 and §2.4 rule 11.
2. **Self-edit previews.** Unchanged: a self-edit still starts after the spoken preview, and the pull request stays the real approval (§3.3, last paragraph).
3. **The drawer's Log tab.** Stays, as history (§4.2).
4. **Fonts.** System fonts, with the sizes in §5.3. Nothing is bundled.
5. **Command Console flag.** On by default on `next` (§2.5), with all four reads made to agree.
