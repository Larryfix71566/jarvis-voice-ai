import XCTest
@testable import MortimerHost

final class GlassAccessibilityTests: XCTestCase {
    func testNormalGlassPreferenceKeepsLiquidSurface() {
        XCTAssertFalse(MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: true, reduceTransparency: false, increasedContrast: false
        ))
    }

    func testReduceTransparencyForcesOpaqueSurface() {
        XCTAssertTrue(MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: true, reduceTransparency: true, increasedContrast: false
        ))
    }

    func testIncreasedContrastForcesOpaqueSurface() {
        XCTAssertTrue(MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: true, reduceTransparency: false, increasedContrast: true
        ))
    }

    func testExplicitGlassRollbackRemainsOpaque() {
        XCTAssertTrue(MortimerGlassAccessibilityPolicy.usesOpaqueSurface(
            glassEnabled: false, reduceTransparency: false, increasedContrast: false
        ))
    }
}
