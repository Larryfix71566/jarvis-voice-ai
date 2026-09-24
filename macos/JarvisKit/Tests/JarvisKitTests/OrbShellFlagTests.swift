import XCTest
@testable import JarvisKit

/// docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D3 — the orb shell rollback
/// lever: default on, either lever turns it off, the environment wins.
final class OrbShellFlagTests: XCTestCase {
    private let key = "JARVIS_ORB_CRYSTAL"

    override func setUp() {
        super.setUp()
        UserDefaults.standard.removeObject(forKey: key)
        unsetenv(key)
    }

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        unsetenv(key)
        super.tearDown()
    }

    func testDefaultsToTheCrystalShell() {
        XCTAssertTrue(JarvisFlags.orbCrystalShellEnabled)
    }

    func testUserDefaultsFalseSelectsTheLegacyShell() {
        UserDefaults.standard.set(false, forKey: key)
        XCTAssertFalse(JarvisFlags.orbCrystalShellEnabled)
    }

    func testEnvironmentOffValuesSelectTheLegacyShell() {
        for raw in ["off", "false", "0", "no", "OFF"] {
            setenv(key, raw, 1)
            XCTAssertFalse(JarvisFlags.orbCrystalShellEnabled, raw)
        }
    }

    func testEnvironmentBeatsUserDefaults() {
        UserDefaults.standard.set(false, forKey: key)
        setenv(key, "on", 1)
        XCTAssertTrue(JarvisFlags.orbCrystalShellEnabled)
    }
}
