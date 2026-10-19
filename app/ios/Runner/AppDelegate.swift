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
    TextRecognitionChannel.register(with: engineBridge.pluginRegistry)
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
    let handler = VNImageRequestHandler(data: data, options: [:])
    try handler.perform([request])
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
