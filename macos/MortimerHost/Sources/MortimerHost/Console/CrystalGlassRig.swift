import CoreGraphics
import Foundation
import JarvisKit

/// Which glass shell the adaptive orb draws
/// (docs/plans/MORTIMER_ORB_CRYSTAL_GLASS_PLAN.md D3).
enum OrbShell: Equatable {
    /// Option A, approved by Larry 2026-09-23: clear, thick-walled glass lit
    /// by a studio window. The default.
    case crystal
    /// The shell exactly as it was before the plan (the 2026-09-18
    /// glass/comet revision), kept verbatim as the rollback.
    case legacy

    /// Resolved once per launch. `JARVIS_ORB_CRYSTAL=off` in the environment,
    /// or `defaults write com.mortimer.host JARVIS_ORB_CRYSTAL -bool false`,
    /// selects `.legacy` from the next launch on.
    static let resolved: OrbShell = JarvisFlags.orbCrystalShellEnabled ? .crystal : .legacy
}

/// Everything about the crystal shell that does not depend on voice state
/// or phase: the constants of the approved preview
/// (docs/interface-research/orb-crystal/glass-orb.html, option A) and the
/// light-rig geometry computed from them. Values are frozen by the plan;
/// change them only with Larry's approval.
enum CrystalGlassRig {
    /// A light's reflection on the sphere, in unit-disc coordinates
    /// (x right, y down; multiply by the sphere radius and add the center).
    struct LightOutline {
        let points: [CGPoint]
        /// Reflection of the light's center; orients its gradient.
        let mid: CGPoint
    }

    // MARK: - Colours (0...255 RGB)

    static let inkRGB: (Double, Double, Double) = (6, 10, 14)
    static let skyRGB: (Double, Double, Double) = (206, 228, 255)
    static let dispersionCoolRGB: (Double, Double, Double) = (110, 215, 255)
    static let dispersionWarmRGB: (Double, Double, Double) = (255, 165, 110)

    // MARK: - Body and wall

    /// Plasma bloom just outside the glass, times voice strength.
    static let haloOpacity = 0.035
    static let haloExtent = 1.2
    static let haloStops: [(location: Double, weight: Double)] = [(0.80, 0), (0.86, 1), (1, 0)]
    /// Glass body: absorbs more toward the edge, where the path is longer.
    static let bodyStops: [(location: Double, opacity: Double)] = [
        (0, 0.04), (0.7, 0.09), (0.88, 0.22), (0.965, 0.34), (1, 0.18),
    ]
    static let plasmaClipFraction = 0.885
    /// Plasma light carried in the wall, strongest opposite the key light.
    static let wallInnerFraction = 0.84
    static let wallOuterFraction = 1.02
    static let wallGlowOpacity = 0.46
    static let wallGlowBlurFraction = 0.035
    static let wallGlowStart = CGPoint(x: -0.2, y: -0.2)
    static let wallGlowEnd = CGPoint(x: 0.75, y: 0.75)
    /// The inner surface of a thick wall reads as a dark line with a faint
    /// light line just outside it.
    static let wallLineFraction = 0.885
    static let wallLineOpacity = 0.38
    static let wallLineWidthFraction = 0.022
    static let wallLineMinWidth = 0.8
    static let wallHighlightOffset = 0.018
    static let wallHighlightOpacity = 0.10
    static let wallHighlightWidth = 0.6

    // MARK: - Reflections (independent of voice state)

    /// Room reflection: sky gradient (top to bottom) masked by Fresnel.
    static let fresnelOpacity = 0.62
    static let skyStops: [(location: Double, opacity: Double)] = [(0, 1), (0.45, 0.55), (0.6, 0.22), (1, 0.10)]
    /// Key light focused through the globe onto the far inner wall.
    static let causticOpacity = 0.24
    static let causticMidOpacityRatio = 0.4
    static let causticCenter = CGPoint(x: 0.50, y: 0.58)
    static let causticRadiusFraction = 0.26
    static let causticBlurFraction = 0.05
    static let causticClipFraction = 0.985
    /// Two-pane window key and rim strip.
    static let keyOpacity = 0.95
    static let stripOpacity = 0.45
    static let lightsBlurFraction = 0.010
    static let lightsMinBlur = 0.35
    static let lightInnerOpacityRatio = 0.55
    static let lightGradientInnerFraction = 0.35
    /// The window seen again off the inside of the far wall.
    static let backKeyOpacity = 0.22
    static let backKeyScale = 0.74
    static let backKeyBlurFraction = 0.03
    /// Faint dispersion along the lit rim.
    static let dispersionStartRadians = -175 * Double.pi / 180
    static let dispersionEndRadians = -95 * Double.pi / 180
    static let dispersionCoolRadius = 1.0
    static let dispersionWarmRadius = 0.982
    static let dispersionCoolPeak = 0.34
    static let dispersionWarmPeak = 0.24
    static let dispersionWidth = 0.9
    static let dispersionBlur = 0.3
    static let arcSegmentCount = 48
    static let arcFalloffExponent = 1.6
    /// Silhouette hairline.
    static let hairlineFraction = 0.996
    static let hairlineOpacity = 0.20
    static let hairlineWidth = 0.7

    // MARK: - Light rig (camera space: x right, y down, z toward the viewer)

    static let keyDirection = SIMD3<Double>(-0.74, -0.70, -0.10)
    static let keyPaneHalfWidth = 0.12
    static let keyPaneHalfHeight = 0.21
    static let keyPaneOffset = 0.14
    static let stripDirection = SIMD3<Double>(0.80, 0.50, -0.30)
    static let stripHalfWidth = 0.10
    static let stripHalfHeight = 0.55
    static let outlineExponent = 6.0
    static let outlineSamples = 96

    static let keyPanes: [LightOutline] = [
        lightOutline(direction: keyDirection, halfWidth: keyPaneHalfWidth,
                     halfHeight: keyPaneHalfHeight, exponent: outlineExponent,
                     offset: -keyPaneOffset),
        lightOutline(direction: keyDirection, halfWidth: keyPaneHalfWidth,
                     halfHeight: keyPaneHalfHeight, exponent: outlineExponent,
                     offset: keyPaneOffset),
    ]
    static let strip: LightOutline = lightOutline(
        direction: stripDirection, halfWidth: stripHalfWidth,
        halfHeight: stripHalfHeight, exponent: outlineExponent, offset: 0)

    /// Schlick's approximation for glass (R0 = 0.04), sampled at these radii.
    static let fresnelSampleRadii: [Double] = [
        0, 0.3, 0.5, 0.65, 0.75, 0.82, 0.87, 0.9, 0.93, 0.95, 0.965, 0.975, 0.985, 0.992, 0.997, 1,
    ]
    static let fresnelStops: [(location: Double, reflectance: Double)] =
        fresnelSampleRadii.map { (location: $0, reflectance: schlick($0)) }

    static func schlick(_ rho: Double) -> Double {
        let cosine = max(0, 1 - rho * rho).squareRoot()
        return 0.04 + 0.96 * pow(1 - cosine, 5)
    }

    /// A distant light in `direction` reflects toward the viewer where the
    /// surface normal is the half vector normalize(direction + view). Its
    /// screen position is that normal's x and y.
    static func mirrorPoint(_ direction: SIMD3<Double>) -> CGPoint {
        let normal = normalized(SIMD3<Double>(direction.x, direction.y, direction.z + 1))
        return CGPoint(x: normal.x, y: normal.y)
    }

    /// A flat rounded-rectangle light (superellipse with `exponent`) facing
    /// the globe along `direction`, shifted sideways by `offset`.
    static func lightOutline(direction: SIMD3<Double>, halfWidth: Double, halfHeight: Double,
                             exponent: Double, offset: Double,
                             samples: Int = outlineSamples) -> LightOutline {
        let axis = normalized(direction)
        let across = normalized(cross(axis, SIMD3<Double>(0, -1, 0)))
        let up = cross(across, axis)
        func at(_ u: Double, _ v: Double) -> SIMD3<Double> {
            normalized(axis + u * across + v * up)
        }
        var points: [CGPoint] = []
        points.reserveCapacity(samples)
        for index in 0..<samples {
            let t = Double(index) / Double(samples) * 2 * Double.pi
            let cu = cos(t), su = sin(t)
            let u = offset + halfWidth * signum(cu) * pow(abs(cu), 2 / exponent)
            let v = halfHeight * signum(su) * pow(abs(su), 2 / exponent)
            points.append(mirrorPoint(at(u, v)))
        }
        return LightOutline(points: points, mid: mirrorPoint(at(offset, 0)))
    }

    private static func signum(_ value: Double) -> Double {
        value > 0 ? 1 : (value < 0 ? -1 : 0)
    }

    private static func normalized(_ v: SIMD3<Double>) -> SIMD3<Double> {
        v / (v * v).sum().squareRoot()
    }

    private static func cross(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> SIMD3<Double> {
        SIMD3<Double>(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
    }
}
