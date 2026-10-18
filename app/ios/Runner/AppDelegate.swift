import Flutter
import UIKit
import Vision

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
    let request = VNClassifyImageRequest()
    let handler = VNImageRequestHandler(data: data, options: [:])
    try handler.perform([request])
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
