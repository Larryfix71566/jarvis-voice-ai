import XCTest

@MainActor
final class PhonePreviewUITests: XCTestCase {
    func testLaunchIsDisconnectedAndDemoRequiresExplicitSelection() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["No synthetic check is running."].exists)
        XCTAssertTrue(app.buttons["preview.run"].exists)
        XCTAssertFalse(app.staticTexts["Synthetic readiness: ready"].exists)
    }

    func testExplicitDemoRemainsVisiblySynthetic() {
        let app = XCUIApplication()
        app.launch()
        app.buttons["preview.run"].tap()

        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Synthetic readiness: ready"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
    }

    func testSyntheticResultsPreviewKeepsDisconnectedNoticeVisible() {
        let app = XCUIApplication()
        app.launch()
        app.buttons["preview.results"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["1 synthetic result(s) — controls ready"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Synthetic result"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
    }

    func testExplicitCardRefreshKeepsCheckedResultsVisible() {
        let app = XCUIApplication()
        app.launch()
        app.buttons["preview.results"].tap()
        XCTAssertTrue(app.staticTexts["1 synthetic result(s) — controls ready"].waitForExistence(timeout: 5))

        app.buttons["preview.cards.refresh"].tap()

        XCTAssertTrue(app.staticTexts["1 synthetic result(s) — controls ready"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Synthetic result"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
    }

    func testLeavingForegroundMasksSyntheticResults() {
        let app = XCUIApplication()
        app.launch()
        app.buttons["preview.results"].tap()
        XCTAssertTrue(app.staticTexts["1 synthetic result(s) — controls ready"].waitForExistence(timeout: 5))

        XCUIDevice.shared.press(.home)
        app.activate()

        XCTAssertTrue(app.staticTexts["No synthetic check is running."].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["1 synthetic result(s) — controls ready"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
    }

    func testAdaptiveNavigationExposesPreviewAndAboutSections() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["Preview"].firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
        var about = app.staticTexts["About"].firstMatch
        if !about.exists {
            let back = app.navigationBars.buttons.firstMatch
            if back.exists { back.tap() }
            about = app.staticTexts["About"].firstMatch
        }
        XCTAssertTrue(about.waitForExistence(timeout: 5))
        about.tap()
        XCTAssertTrue(app.staticTexts["Preview only"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
    }
    func testFiveMobileViewActionsKeepSourceAndSyntheticBanner() {
        let app = XCUIApplication(); app.launch()
        app.buttons["preview.results"].tap()
        let id = "00000000-0000-0000-0000-000000000101"
        for action in ["select", "pin", "unpin", "close", "reopen"] {
            let button = app.buttons["preview.card.results.\(action).\(id)"]
            XCTAssertTrue(button.waitForExistence(timeout: 5)); XCTAssertTrue(button.isEnabled)
            button.tap()
            XCTAssertTrue(app.staticTexts["Synthetic result"].waitForExistence(timeout: 5))
            XCTAssertTrue(app.descendants(matching: .any)["preview.disconnected-notice"].exists)
            if action == "pin" { XCTAssertTrue(app.staticTexts["Pinned on phone"].exists) }
            if action == "close" { XCTAssertFalse(app.staticTexts["Selected on phone"].exists) }
        }
        XCTAssertTrue(app.staticTexts["Selected on phone"].exists)
    }

}
