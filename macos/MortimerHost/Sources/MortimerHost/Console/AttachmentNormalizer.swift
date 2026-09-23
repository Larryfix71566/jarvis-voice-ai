import Foundation
import CryptoKit
import JarvisKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

enum AttachmentNormalizer {
    static let maxTextCharacters = 12_000
    static let maxImageBytes = 8 * 1024 * 1024
    static let maxImageDimension = 8_192

    static func text(_ value: String) -> SharedContentTransfer? {
        let clean = value.unicodeScalars.filter { $0.value >= 0x20 || $0.value == 0x09 || $0.value == 0x0A }.map(String.init).joined().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= maxTextCharacters else { return nil }
        let data = Data(clean.utf8)
        return SharedContentTransfer(kind: .text, mimeType: "text/plain", digest: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), payload: data)
    }

    /// Decode and re-encode an image before staging it. ImageIO verifies the
    /// actual format (so a MIME spoof or truncated file is rejected), applies
    /// the source orientation while creating the CGImage, and writing only
    /// that image to a fresh PNG strips EXIF/GPS metadata. The staged payload
    /// is therefore always bounded, portable and safe to hand to the shared
    /// content transport.
    static func image(_ data: Data, mimeType: String) -> SharedContentTransfer? {
        guard !data.isEmpty, data.count <= maxImageBytes,
              ["image/png", "image/jpeg", "image/heic", "image/heif", "image/webp"].contains(mimeType.lowercased()),
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) > 0,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
              let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
              width.intValue > 0, height.intValue > 0,
              width.intValue <= maxImageDimension, height.intValue <= maxImageDimension,
              let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: maxImageDimension,
                kCGImageSourceShouldCache: false,
                kCGImageSourceShouldAllowFloat: false,
              ] as CFDictionary) else { return nil }

        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.png.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(destination, cgImage, nil)
        guard CGImageDestinationFinalize(destination) else { return nil }
        let normalized = output as Data
        guard !normalized.isEmpty, normalized.count <= maxImageBytes else { return nil }
        return SharedContentTransfer(kind: .image, mimeType: "image/png",
                                     digest: SHA256.hash(data: normalized).map { String(format: "%02x", $0) }.joined(), payload: normalized)
    }
}
