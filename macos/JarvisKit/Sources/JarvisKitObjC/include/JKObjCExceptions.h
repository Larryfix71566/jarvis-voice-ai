#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// WS-18: runs `block` and returns the Objective-C exception it raised, or
/// nil when it returned normally. Swift cannot catch NSException; some
/// AVFoundation calls (AVAudioPlayerNode.play after an output-device switch:
/// "player did not see an IO cycle", 2026-09-30) report failure only that
/// way, which otherwise terminates the app.
FOUNDATION_EXPORT NSException * _Nullable JKCatchObjCException(NS_NOESCAPE void (^block)(void));

NS_ASSUME_NONNULL_END
