---
date: 2026-10-06
system: codex
rows: [WS-17, WS-20, WS-21, WS-05]
prs: [173, 172, 174, 184, 185]
---

Larry resumed the goal to complete work that does not need him. Fetched main is `a4ad5a4`: #184 merged with all five checks green. The WS-20 checklist branch is now recorded as a merged event, removing the new merged-branch checker finding; WS-10/11 owner wording remains for #174.

Assigned CC7a.3 review (#173 `fb2e06f`) is recorded at https://github.com/Larryfix71566/jarvis-voice-ai/pull/173#issuecomment-6027496087. Three blocking P2 findings: live numbered references can close a newly arrived result because the bridge stamps the latest inventory revision; real pipeline acknowledgement drops numbered ambiguity choices; open Older results lose console Close access. Existing focused Python10/native13 tests pass. An independent actual-wire native witness fails two safety assertions with outcome `applied`; a second witness confirms the Older omission. Public synthetic probes independently capture exact callback choice loss and a separately documented pre-existing voice-comparison secondary-target rejection.

Review artifacts remain in `/private/tmp/cc7a3-review-probes.py`, `/private/tmp/cc7a3-review-python-evidence.json`, `/private/tmp/cc7a3-native-review-probes.swift`, `/private/tmp/cc7a3-voice-renumber-request.json`, and `/private/tmp/cc7a3-review-fb2e06f-swift-native.log`. The isolated review source is unchanged except its two temporary witnesses; production and provider settings are unchanged. Default swiftbuild stopped at dependency codesigning; using the pinned cached artifact with symlinks preserved and native SwiftPM completed the focused review run, so no full-suite or deployment pass is inferred.

#172 and #174 have ROADMAP conflicts against `a4ad5a4`; owner follow-up must preserve #184's checklists, current WS-05 merged status and verified B1 facts. #172's remaining-deploy wording also contradicts the successful bde22bb receipt. Physical acceptance, Claude implementation fixes/review, source authorization, operator-issued identity, native-test assignment and account/rollout decisions remain open. This resumed goal turn makes review/handoff progress; no blocked or complete goal status is inferred.

## Reproduction artifacts for the implementation owner

These public synthetic witnesses are embedded here so Claude can obtain them from PR #185 without Larry transferring local files. They are review evidence, not production code or acceptance fixtures. Their source under review is frozen at PR #173 head `fb2e06f02544c26031bd293f2af0d81ac0a69b6f`.

The Python witness compiles the actual `handle_console_result` body from that source and calls the real console-action builder; only the envelope unwrap is an identity adapter for the already-unwrapped public message. It intentionally asserts the **observed defects** and therefore exits successfully on the defective head. When adopting regression coverage, assert the desired preservation/refusal behavior instead. It does not establish a whole live bot/session test. The native race witness already asserts the **intended safety** and fails on that head; its two failed assertions are one failing test, not two separate tests. The Older witness confirms store membership plus the source-reviewed menu omission, not a live pointer/VoiceOver acceptance result. Preserve all original test assertions while adding complete bridge coverage.

To reproduce in an isolated checkout, set the Python witness's `root` to that checkout and run it with the checkout on `PYTHONPATH`; it generates the public `/private/tmp/cc7a3-voice-renumber-request.json` consumed by the Swift witness. Copy the Swift witness into only the disposable checkout's test target and run the filtered `CC7a3` tests. No vault, service credential, provider, app launch or production write is required. Native dependency/cache setup must preserve framework symlinks; on this Mac the pinned artifact plus `swift test --disable-sandbox --skip-update --build-system native --filter CC7a3` completed after the default build engine stopped at codesigning. That local build-system disposition is not a product change.

<details>
<summary>Python transport and wire witnesses</summary>

```python
"""Public synthetic review probes; no provider, production or network actions."""
import ast
import asyncio
import json
from pathlib import Path
from typing import Any
from jarvis.bot.console_actions import build_console_action_tool

root=Path('/private/tmp/cc7a3-review-fb2e06f')
source=root/'jarvis/bot/pipeline.py'
tree=ast.parse(source.read_text())
callback=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='handle_console_result')
code=compile(ast.fix_missing_locations(ast.Module(body=[callback],type_ignores=[])),str(source),'exec')
ids={'session_id':'00000000-0000-4000-8000-000000000001','generation':'00000000-0000-4000-8000-000000000002'}

async def probes():
    loop=asyncio.get_running_loop()
    sent=[]
    waiters={}
    namespace={'Any':Any,'_unwrap_client_message':lambda x:x,'console_waiters':waiters}
    exec(code,namespace)
    live_callback=namespace['handle_console_result']
    async def push(message):sent.append(message)
    async def wait(request_id):
        future=loop.create_future();waiters[request_id]=future
        await live_callback({'type':'console/result','request_id':request_id,
            'status':'needs_choice','code':'ambiguous_result',
            'summary':'More than one result matches. Ask which one, by number.',
            'choices':[{'id':'public-a','label':'1 Weather Folly Beach 5m'},
                       {'id':'public-b','label':'2 Weather Folly Beach 1h'}]})
        resolved=await future
        assert 'choices' not in resolved
        return resolved
    _,handler=build_console_action_tool(push,await_result=wait,**ids)
    text=await handler({'action':'result_select','target':'Folly Beach'})
    assert '1 Weather Folly Beach' not in text and '2 Weather Folly Beach' not in text

    state={'revision':1}
    async def ack(_):return {'status':'ok','summary':'Console action applied.'}
    _,race=build_console_action_tool(push,revision=lambda:state['revision'],await_result=ack,**ids)
    observed={'revision':1,'results':[{'id':'public-bravo','number':1,'title':'Bravo'}]}
    state['revision']=2
    await race({'action':'result_close','target':'1'})
    captured=sent[-1]
    assert captured['revision']==2 and captured['target']=='1' and captured['revision']!=observed['revision']
    Path('/private/tmp/cc7a3-voice-renumber-request.json').write_text(json.dumps(captured))

    before=len(sent)
    comparison=await race({'action':'compare_set','target':'1','secondary_target':'2'})
    assert 'secondary target' in comparison.lower() and len(sent)==before
    output={'head':'fb2e06f','exact_callback_choice_loss':text,
      'number_race':{'observed_revision':1,'sent_revision':captured['revision'],'sent_target':captured['target']},
      'compare_rejection':comparison,'real_callback_source_lines':[callback.lineno,callback.end_lineno],
      'provider_calls':0,'production_changes':0}
    Path('/private/tmp/cc7a3-review-python-evidence.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))

asyncio.run(probes())
```

</details>

<details>
<summary>Native wrong-target safety regression and Older membership witness</summary>

```swift
import XCTest
import JarvisKit
@testable import MortimerHost

/// Independent review witnesses; temporary, not implementation changes.
@MainActor
final class CC7a3NativeReviewProbes: XCTestCase {
    private func make(_ title: String, at date: Date) -> WorkspaceResult {
        let bytes = try! JSONSerialization.data(withJSONObject:["kind":"markdown","title":title,"body":"Public fixture"])
        return WorkspaceResult(payload:try! JSONDecoder().decode(DisplayPayload.self,from:bytes),receivedAt:date)
    }
    func testActualPythonStampedNumberCannotCloseANewArrival() throws {
        let store=WorkspaceStore()
        let old=make("Bravo",at:Date(timeIntervalSince1970:1))
        store.receive(old,quietly:true)
        XCTAssertEqual(store.consoleRevision,1)
        XCTAssertEqual(store.recents.entries.first?.id,old.id)
        let new=make("Charlie",at:Date(timeIntervalSince1970:2))
        store.receive(new,quietly:true)
        XCTAssertEqual(store.consoleRevision,2)
        let wire=try Data(contentsOf:URL(fileURLWithPath:"/private/tmp/cc7a3-voice-renumber-request.json"))
        let request=try JSONDecoder().decode(ConsoleRequest.self,from:wire)
        let drawer=DrawerState()
        let coordinator=ConsoleActionCoordinator(workspace:store,display:DisplayWindowStore(),placement:WindowPlacement(drawer:drawer,windows:WindowActions()),drawer:drawer,screens:{[]})
        let outcome=coordinator.execute(request)
        XCTAssertTrue(store.containsResult(new.id),"The result that arrived after the referenced inventory must not be closed; got \(outcome)")
        XCTAssertEqual(outcome,.stale,"Observed inventory was revision1; actual Python wire stamps revision2 and raw number1")
    }
    func testOpenedOlderResultIsAbsentFromCloseAndCompareEntryLists() {
        let store=WorkspaceStore()
        let results=(0..<11).map {make("Public \($0)",at:Date(timeIntervalSince1970:Double($0)))}
        for r in results {store.receive(r,quietly:true)}
        let oldest=results[0]
        store.select(oldest.id)
        XCTAssertEqual(store.activeID,oldest.id)
        XCTAssertTrue(store.recents.older.contains(where:{$0.id==oldest.id}))
        XCTAssertFalse(store.recents.entries.contains(where:{$0.id==oldest.id}),"Current Close menu iterates precisely these entries; Older only offers Select")
        XCTAssertEqual(store.results.count,11)
    }
}
```

</details>

<details>
<summary>Observed Python evidence at the reviewed head</summary>

```json
{
  "head": "fb2e06f",
  "exact_callback_choice_loss": "More than one result matches. Ask which one, by number.",
  "number_race": {
    "observed_revision": 1,
    "sent_revision": 2,
    "sent_target": "1"
  },
  "compare_rejection": "Console action rejected: console action requires a secondary target.",
  "real_callback_source_lines": [
    1941,
    1956
  ],
  "provider_calls": 0,
  "production_changes": 0
}
```

</details>

Recorded native outcome: all 13 original Recents tests pass; the wrong-target safety witness fails because Charlie is closed with outcome `applied`, while the Older membership witness passes. These results reproduce review defects; they do not certify the corrected implementation or close live acceptance.

Verbatim artifact SHA-256 checks (source file and extracted fence are byte-identical):

- python: `5e44c62118dcfa9ec4a7b116ada8653f894e998e533737dedf5106c520225e9f`
- swift: `fefd893c11943a31018cbf585fd3ad07f5c0d7ac968db1eeed859c4b3516c8dc`
- json: `123dae69760857dd91b289b67517acfe8d8ab9932d29672cd4c8c9de878d19d4`
