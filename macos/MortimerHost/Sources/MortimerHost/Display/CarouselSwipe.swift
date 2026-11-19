import CoreGraphics
import Foundation

/// Pure swipe maths for the result carousel. No AppKit or SwiftUI so it is
/// trivially testable. Numbers match the approved carousel-glass mockup.
struct CarouselSwipeModel {
    /// Fraction of the card width a drag must cover to commit.
    static let commitFraction: CGFloat = 0.28
    /// Flick speed (points per second) that commits regardless of distance.
    static let flickVelocity: CGFloat = 500
    /// Rubber-band travel never exceeds this fraction of the width.
    static let bandFraction: CGFloat = 0.18

    /// Horizontal offset for a drag of `translation`. Follows the finger 1:1
    /// while a neighbour exists in that direction and rubber-bands (bounded)
    /// past the first or last card. Dragging right moves toward the previous card.
    static func offset(translation: CGFloat, index: Int, count: Int, width: CGFloat) -> CGFloat {
        guard width > 0, translation != 0 else { return 0 }
        let hasTarget = translation < 0 ? index + 1 < count : index > 0
        if hasTarget { return min(max(translation, -width), width) }
        let limit = bandFraction * width
        let magnitude = abs(translation)
        let banded = limit * (1 - 1 / (magnitude / limit * 0.55 + 1))
        return translation < 0 ? -banded : banded
    }

    /// -1 previous, 0 stay, +1 next. Dragging left (negative) means next.
    /// One card per swipe; never past the ends. `predictedEnd` is accepted for
    /// call-site symmetry with DragGesture; the decision uses translation and velocity.
    static func decision(translation: CGFloat, predictedEnd: CGFloat, velocity: CGFloat,
                         index: Int, count: Int, width: CGFloat) -> Int {
        guard width > 0 else { return 0 }
        let direction: CGFloat = translation != 0 ? (translation < 0 ? -1 : 1) : (velocity < 0 ? -1 : (velocity > 0 ? 1 : 0))
        guard direction != 0 else { return 0 }
        let sameDirectionFlick = abs(velocity) >= flickVelocity && (velocity < 0) == (direction < 0)
        let farEnough = abs(translation) / width >= commitFraction
        guard farEnough || sameDirectionFlick else { return 0 }
        let step = direction < 0 ? 1 : -1
        let target = index + step
        return (target >= 0 && target < count) ? step : 0
    }
}

enum ScrollSwipePhase: Equatable { case began, changed, ended, cancelled }

/// Turns trackpad two-finger scroll and mouse-wheel events into swipe state.
/// Natural scrolling: event deltas are used as given, so content follows the fingers.
struct ScrollSwipeAccumulator {
    struct Output: Equatable {
        /// Current drag translation to render (0 when idle).
        var translation: CGFloat = 0
        /// True when the event belongs to a horizontal swipe and should be consumed.
        var claimed = false
        /// -1/0/+1 card step to apply now.
        var commit = 0
        /// The gesture is over; the view should settle back to rest.
        var finished = false
    }

    static let probeDistance: CGFloat = 12
    static let dominance: CGFloat = 1.5
    static let wheelCooldown: TimeInterval = 0.35

    private(set) var translation: CGFloat = 0
    private var probeX: CGFloat = 0
    private var probeY: CGFloat = 0
    private var decided = false
    private var claimed = false
    private var swallowMomentum = false
    private var lastWheelStep: TimeInterval = -.infinity

    mutating func feed(deltaX: CGFloat, deltaY: CGFloat, phase: ScrollSwipePhase,
                       momentum: Bool, precise: Bool, timestamp: TimeInterval,
                       index: Int, count: Int, width: CGFloat) -> Output {
        if !precise { return wheel(deltaX: deltaX, deltaY: deltaY, timestamp: timestamp,
                                   index: index, count: count, width: width) }
        if momentum { return Output(claimed: swallowMomentum) }
        switch phase {
        case .began:
            reset()
            swallowMomentum = false
        case .cancelled:
            let was = claimed
            reset()
            swallowMomentum = false
            return Output(claimed: was, finished: was)
        case .ended:
            guard claimed else { reset(); return Output() }
            let step = CarouselSwipeModel.decision(translation: translation, predictedEnd: translation, velocity: 0,
                                                   index: index, count: count, width: width)
            reset()
            swallowMomentum = true
            return Output(claimed: true, commit: step, finished: true)
        case .changed:
            break
        }
        if !decided {
            probeX += deltaX
            probeY += deltaY
            guard max(abs(probeX), abs(probeY)) >= Self.probeDistance else { return Output() }
            decided = true
            claimed = abs(probeX) > Self.dominance * abs(probeY)
            guard claimed else { return Output() }
            translation = probeX
            return Output(translation: translation, claimed: true)
        }
        guard claimed else { return Output() }
        translation += deltaX
        return Output(translation: translation, claimed: true)
    }

    private mutating func wheel(deltaX: CGFloat, deltaY: CGFloat, timestamp: TimeInterval,
                                index: Int, count: Int, width: CGFloat) -> Output {
        guard deltaX != 0, abs(deltaX) > abs(deltaY) else { return Output() }
        guard timestamp - lastWheelStep >= Self.wheelCooldown else { return Output(claimed: true) }
        let step = deltaX < 0 ? 1 : -1
        let target = index + step
        guard target >= 0, target < count else { return Output(claimed: true) }
        lastWheelStep = timestamp
        return Output(claimed: true, commit: step, finished: true)
    }

    private mutating func reset() {
        translation = 0
        probeX = 0
        probeY = 0
        decided = false
        claimed = false
    }
}
