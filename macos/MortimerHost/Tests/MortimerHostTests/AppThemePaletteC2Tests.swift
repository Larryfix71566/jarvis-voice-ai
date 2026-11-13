import XCTest
import SwiftUI
import AppKit
@testable import MortimerHost

final class AppThemePaletteC2Tests: XCTestCase {
    private struct RGB: Equatable {
        let red: Double
        let green: Double
        let blue: Double
        let alpha: Double

        init(red: Double, green: Double, blue: Double, alpha: Double = 1) {
            self.red = red
            self.green = green
            self.blue = blue
            self.alpha = alpha
        }
    }

    private func rgb(_ color: Color, file: StaticString = #filePath, line: UInt = #line) throws -> RGB {
        let color = try XCTUnwrap(NSColor(color).usingColorSpace(.sRGB), file: file, line: line)
        return RGB(red: Double(color.redComponent), green: Double(color.greenComponent),
                   blue: Double(color.blueComponent), alpha: Double(color.alphaComponent))
    }

    private func assertRGB(_ color: Color, _ expected: RGB, _ name: String,
                           file: StaticString = #filePath, line: UInt = #line) throws {
        let actual = try rgb(color, file: file, line: line)
        XCTAssertEqual(actual.red, expected.red, accuracy: 0.0001, "\(name) red", file: file, line: line)
        XCTAssertEqual(actual.green, expected.green, accuracy: 0.0001, "\(name) green", file: file, line: line)
        XCTAssertEqual(actual.blue, expected.blue, accuracy: 0.0001, "\(name) blue", file: file, line: line)
        XCTAssertEqual(actual.alpha, expected.alpha, accuracy: 0.0001, "\(name) alpha", file: file, line: line)
    }

    private func composite(_ foreground: RGB, over background: RGB) -> RGB {
        RGB(red: foreground.red * foreground.alpha + background.red * (1 - foreground.alpha),
            green: foreground.green * foreground.alpha + background.green * (1 - foreground.alpha),
            blue: foreground.blue * foreground.alpha + background.blue * (1 - foreground.alpha))
    }

    private func luminance(_ color: RGB) -> Double {
        func linear(_ component: Double) -> Double {
            component <= 0.04045 ? component / 12.92 : pow((component + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(color.red) + 0.7152 * linear(color.green) + 0.0722 * linear(color.blue)
    }

    private func contrast(_ foreground: RGB, _ background: RGB) -> Double {
        let first = luminance(foreground), second = luminance(background)
        return (max(first, second) + 0.05) / (min(first, second) + 0.05)
    }

    func testApprovedPaletteAndExistingSemanticColors() throws {
        try assertRGB(AppTheme.listening, RGB(red: 102 / 255, green: 115 / 255, blue: 1), "listening")
        try assertRGB(AppTheme.user, RGB(red: 45 / 255, green: 212 / 255, blue: 191 / 255), "user")
        try assertRGB(AppTheme.mortimer, RGB(red: 224 / 255, green: 112 / 255, blue: 32 / 255), "mortimer")
        try assertRGB(AppTheme.ok, RGB(red: 166 / 255, green: 1, blue: 193 / 255), "ok")
        try assertRGB(AppTheme.approval, RGB(red: 1, green: 216 / 255, blue: 74 / 255), "approval")
        try assertRGB(AppTheme.error, RGB(red: 1, green: 89 / 255, blue: 139 / 255), "error")

        try assertRGB(AppTheme.amber, RGB(red: 1, green: 180 / 255, blue: 84 / 255), "amber")
        try assertRGB(AppTheme.green, RGB(red: 61 / 255, green: 220 / 255, blue: 151 / 255), "green")
        try assertRGB(AppTheme.red, RGB(red: 1, green: 95 / 255, blue: 86 / 255), "red")
        XCTAssertEqual(try rgb(AppTheme.attn), try rgb(AppTheme.amber))
    }

    func testSpeakerTokensReuseAudioPresentationColors() throws {
        XCTAssertEqual(try rgb(AppTheme.user), try rgb(AudioPresentationTuning.userColor))
        XCTAssertEqual(try rgb(AppTheme.mortimer), try rgb(AudioPresentationTuning.assistantColor))
    }

    func testEveryNewTokenMeetsNonTextContrastOnGlassAndOpaqueFallbacks() throws {
        let tokens = [
            ("listening", AppTheme.listening),
            ("user", AppTheme.user),
            ("mortimer", AppTheme.mortimer),
            ("ok", AppTheme.ok),
            ("approval", AppTheme.approval),
            ("error", AppTheme.error),
        ]
        let appBackground = try rgb(AppTheme.bg)
        let surfaces = [
            ("glass over app background", appBackground),
            ("regular glass tint", composite(try rgb(AppTheme.glassBg), over: appBackground)),
            ("heavy glass tint", composite(try rgb(AppTheme.glassBgHeavy), over: appBackground)),
            ("glass-off fallback", composite(try rgb(AppTheme.panelOpaque), over: appBackground)),
            ("Reduce Transparency / Increase Contrast fallback", try rgb(AppTheme.panelSolid)),
        ]

        for (tokenName, token) in tokens {
            let foreground = try rgb(token)
            for (surfaceName, surface) in surfaces {
                XCTAssertGreaterThanOrEqual(
                    contrast(foreground, surface), 3.0,
                    "\(tokenName) on \(surfaceName) must meet the 3:1 non-text minimum"
                )
            }
        }
    }
}
