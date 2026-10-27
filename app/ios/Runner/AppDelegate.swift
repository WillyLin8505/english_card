import Flutter
import UIKit
import Vision
import ImageIO
import os

/// Vision decodes the whole file it is given: a 12 MP camera photo costs
/// ~48 MB, and the accurate text reader several times that, which pushed the
/// app past iOS's ~2 GB per-app limit on a 4 GB iPhone (問題回報 #418, signal
/// 9 / Jetsam per-process-limit). The classifier works on a ~300 px copy and
/// text stays legible at 2048 px, so both read a copy with the long side at
/// most [maxSide]. The thumbnail has EXIF rotation applied; boxes are
/// fractions of the image, so they still match the picture as shown.
func downsampledImage(_ data: Data, maxSide: Int = 2048) -> CGImage? {
  let opts = [kCGImageSourceShouldCache: false] as CFDictionary
  guard let source = CGImageSourceCreateWithData(data as CFData, opts) else { return nil }
  let thumbOpts = [
    kCGImageSourceCreateThumbnailFromImageAlways: true,
    kCGImageSourceCreateThumbnailWithTransform: true,
    kCGImageSourceShouldCacheImmediately: true,
    kCGImageSourceThumbnailMaxPixelSize: maxSide,
  ] as CFDictionary
  return CGImageSourceCreateThumbnailAtIndex(source, 0, thumbOpts)
}

/// A request handler on the downsampled picture, or on the raw data if it
/// cannot be decoded that way.
func visionHandler(_ data: Data) -> VNImageRequestHandler {
  if let image = downsampledImage(data) {
    return VNImageRequestHandler(cgImage: image, options: [:])
  }
  return VNImageRequestHandler(data: data, options: [:])
}

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    LocalVisionChannel.register(with: engineBridge.pluginRegistry)
    TextRecognitionChannel.register(with: engineBridge.pluginRegistry)
    MemoryChannel.register(with: engineBridge.pluginRegistry)
  }
}

/// On-device photo recognition for `lib/services/local_vision.dart`
/// (問題回報 #265, owner decision 2026-10-18: 本機辨識＋內建詞庫). Apple
/// Vision's image classifier labels the whole picture (about 1,300 nouns and
/// scenes); the Dart side turns the labels into vocabulary candidates with
/// the bundled dictionary. Nothing leaves the phone.
///
/// Channel `photo_english/local_vision`:
///   available            → Bool
///   classify {image: bytes, maxResults: Int} → [{label: String, confidence: Double}]
enum LocalVisionChannel {
  static let name = "photo_english/local_vision"

  static func register(with registry: FlutterPluginRegistry) {
    guard let registrar = registry.registrar(forPlugin: "LocalVisionChannel") else { return }
    let channel = FlutterMethodChannel(name: name, binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "available":
        result(true)
      case "classify":
        guard let args = call.arguments as? [String: Any],
              let image = args["image"] as? FlutterStandardTypedData else {
          result(FlutterError(code: "bad_args", message: "image bytes required", details: nil))
          return
        }
        let maxResults = args["maxResults"] as? Int ?? 60
        DispatchQueue.global(qos: .userInitiated).async {
          do {
            let labels = try classify(image.data, maxResults: maxResults)
            DispatchQueue.main.async { result(labels) }
          } catch {
            DispatchQueue.main.async {
              result(FlutterError(code: "vision", message: error.localizedDescription, details: nil))
            }
          }
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// Labels for one JPEG/PNG, best first. Keeps the labels Vision itself
  /// rates as reliable (90% precision) plus anything it is at least half
  /// sure of, so a plain photo still yields a handful of words.
  static func classify(_ data: Data, maxResults: Int) throws -> [[String: Any]] {
    try autoreleasepool {
      let request = VNClassifyImageRequest()
      try visionHandler(data).perform([request])
      let observations = (request.results as? [VNClassificationObservation]) ?? []
      var out: [[String: Any]] = []
      for o in observations {
        guard o.hasMinimumRecall(0.01, forPrecision: 0.9) || o.confidence >= 0.5 else { continue }
        out.append(["label": o.identifier, "confidence": Double(o.confidence)])
        if out.count >= maxResults { break }
      }
      return out
    }
  }
}

/// On-device text reading for `lib/services/text_scan.dart` (問題回報 #324:
/// 拍文字擷取單字). Apple Vision's `VNRecognizeTextRequest` reads signs,
/// menus and book pages; the Dart side cuts the English words out, turns
/// them into dictionary forms and frames them on the photo. Nothing leaves
/// the phone.
///
/// Channel `photo_english/text_recognition`:
///   available           → Bool
///   recognize {image: bytes} → [{text, confidence, box: [x, y, w, h],
///                                words: [{text, box}]}]
/// Boxes are fractions of the image with the origin at the top left.
enum TextRecognitionChannel {
  static let name = "photo_english/text_recognition"

  static func register(with registry: FlutterPluginRegistry) {
    guard let registrar = registry.registrar(forPlugin: "TextRecognitionChannel") else { return }
    let channel = FlutterMethodChannel(name: name, binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "available":
        result(true)
      case "recognize":
        guard let args = call.arguments as? [String: Any],
              let image = args["image"] as? FlutterStandardTypedData else {
          result(FlutterError(code: "bad_args", message: "image bytes required", details: nil))
          return
        }
        DispatchQueue.global(qos: .userInitiated).async {
          do {
            let lines = try recognize(image.data)
            DispatchQueue.main.async { result(lines) }
          } catch {
            DispatchQueue.main.async {
              result(FlutterError(code: "vision", message: error.localizedDescription, details: nil))
            }
          }
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// Vision's boxes are normalized with the origin at the bottom left.
  static func topLeft(_ r: CGRect) -> [Double] {
    [Double(r.minX), Double(1 - r.maxY), Double(r.width), Double(r.height)]
  }

  static func recognize(_ data: Data) throws -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = true
    // Photos from the camera carry their rotation in EXIF; Vision reads it
    // from the image data, so boxes match the picture as shown.
    try visionHandler(data).perform([request])
    var out: [[String: Any]] = []
    for o in request.results ?? [] {
      guard let top = o.topCandidates(1).first else { continue }
      let text = top.string
      var words: [[String: Any]] = []
      text.enumerateSubstrings(in: text.startIndex..<text.endIndex, options: .byWords) { word, range, _, _ in
        guard let word = word,
              let box = try? top.boundingBox(for: range)?.boundingBox else { return }
        words.append(["text": word, "box": topLeft(box)])
      }
      out.append([
        "text": text,
        "confidence": Double(top.confidence),
        "box": topLeft(o.boundingBox),
        "words": words,
      ])
    }
    return out
  }
}

/// Memory numbers for `lib/services/memory_monitor.dart` (問題回報 #824):
/// a 4 GB iPhone closes the app near ~2 GB, and the simulator has no limit,
/// so the app watches how close it is and reports before it is closed.
///
/// Channel `photo_english/memory`:
///   snapshot → {available: Int, footprint: Int} in bytes. `available` is
///              os_proc_available_memory() (0 where there is no limit, as on
///              the simulator); `footprint` is task_vm_info.phys_footprint,
///              the number Jetsam compares with the limit (-1 if unknown).
///   device   → {model: String, system: String} ("iPhone13,2", "18.1").
enum MemoryChannel {
  static let name = "photo_english/memory"

  static func register(with registry: FlutterPluginRegistry) {
    guard let registrar = registry.registrar(forPlugin: "MemoryChannel") else { return }
    let channel = FlutterMethodChannel(name: name, binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "snapshot":
        result([
          "available": Int(os_proc_available_memory()),
          "footprint": footprint() ?? -1,
        ])
      case "device":
        result(["model": model(), "system": UIDevice.current.systemVersion])
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  static func footprint() -> Int? {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(
      MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
      $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
        task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
      }
    }
    return kr == KERN_SUCCESS ? Int(info.phys_footprint) : nil
  }

  /// The hardware id ("iPhone13,2"); the simulated one on the simulator.
  static func model() -> String {
    if let simulated = ProcessInfo.processInfo.environment["SIMULATOR_MODEL_IDENTIFIER"] {
      return "\(simulated) (Simulator)"
    }
    var info = utsname()
    uname(&info)
    return withUnsafeBytes(of: &info.machine) { raw in
      String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
    }
  }
}
