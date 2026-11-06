import Foundation
import PhoneRemoteAuthority
import Darwin

let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 11, args[0] == "--test-owner",
      let grantCount = Int(args[6]), grantCount >= 0,
      let holdMS = UInt32(args[7]), holdMS <= 60_000, let hostGeneration = UInt64(args[8]), hostGeneration > 0,
      let loginCounter = UInt64(args[9]) else {
    fputs("test-only owner arguments required\n", stderr)
    exit(64)
}
do {
    let code = try PhoneRemoteAuthorityOwner.runOfflineTestOwner(
        lockPath: args[1], python: args[2], database: args[3],
        workingDirectory: args[4], scenario: args[5], expectedGrants: grantCount,
        holdMilliseconds: holdMS, readyPath: ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_READY_FILE"] ?? "",
        testHostGeneration: hostGeneration, testLoginCounter: loginCounter, testAnchorPath: args[10]
    )
    exit(code)
} catch {
    fputs("authority owner unavailable\n", stderr)
    exit(70)
}
