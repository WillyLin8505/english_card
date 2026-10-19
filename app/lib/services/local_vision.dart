import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../models/learning_card.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'cefr_lexicon.dart';
import 'lexicon_pack.dart';
import 'tagging_service.dart';

/// One label from the device's image classifier, e.g. (`banana`, 0.93).
typedef VisionLabel = ({String label, double confidence});

/// Shown when the phone's classifier fails on a photo. The simulator has no
/// neural engine, so this is common there; a real phone rarely hits it.
const visionFailedMessage = '手機暫時無法辨識這張照片（模擬器上常見，實機可能正常），請換一張照片再試';

/// On-device picture recognition (問題回報 #265, owner decision 2026-10-18:
/// B+C 本機辨識＋內建詞庫). iOS answers through Apple Vision's image
/// classifier (`VNClassifyImageRequest`, ~1,300 labels) registered on the
/// `photo_english/local_vision` channel in `ios/Runner/AppDelegate.swift`.
/// Android has no classifier yet and reports itself unavailable; the web
/// build keeps using the page's own tagging server.
class LocalVision {
  static const channel = MethodChannel('photo_english/local_vision');

  /// Replaces the platform channel: tests and other front ends.
  static Future<List<VisionLabel>> Function(Uint8List jpeg, int maxResults)?
      classifier;

  /// Asks the platform once at start-up; [AppSettings.localRecognition]
  /// mirrors the answer.
  static Future<bool> probe() async {
    if (kIsWeb) return false;
    try {
      return await channel.invokeMethod<bool>('available') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static Future<List<VisionLabel>> classify(Uint8List jpeg,
      {int maxResults = 60}) async {
    final custom = classifier;
    if (custom != null) return custom(jpeg, maxResults);
    final List<Object?>? raw;
    try {
      raw = await channel.invokeListMethod<Object?>(
          'classify', {'image': jpeg, 'maxResults': maxResults});
    } on PlatformException catch (e) {
      // The platform's own text (e.g. "Failed to create espresso context.")
      // is for developers; the learner gets a plain sentence (問題回報 #370).
      debugPrint('local vision failed: ${e.code} ${e.message}');
      throw TaggingApiException(visionFailedMessage);
    } on MissingPluginException {
      throw TaggingApiException('這台裝置沒有本機照片辨識');
    }
    return [
      for (final item in raw ?? const [])
        if (item is Map && item['label'] is String)
          (
            label: item['label'] as String,
            confidence: (item['confidence'] as num?)?.toDouble() ?? 0,
          ),
    ];
  }
}

/// Where the i-th of n labels sits on the photo. The classifier sees the
/// whole picture and gives no positions, so labels fan out from the centre
/// (a golden-angle spiral) instead of piling up on one point.
LabelPoint spreadPoint(int i, int n) {
  if (n <= 1) return const LabelPoint(0.5, 0.5);
  final r = 0.08 + 0.28 * math.sqrt(i / (n - 1));
  final a = i * 2.399963;
  return LabelPoint(
    (0.5 + r * math.cos(a)).clamp(0.12, 0.88),
    (0.5 + r * math.sin(a)).clamp(0.12, 0.88),
  );
}

/// Classifier labels → candidates the learner's resources know (the
/// language pack or the CEFR word list), highest confidence first, nudged
/// toward [level]. Vision's `golden_retriever` style names become words.
List<WordCandidate> candidatesFromLabels(
  List<VisionLabel> labels, {
  required CefrLexicon lexicon,
  required String level,
  LexiconPack? pack,
  String? focus,
  List<String> exclude = const [],
  int maxCandidates = LocalVisionTagger.maxCandidates,
  double minConfidence = LocalVisionTagger.minConfidence,
}) {
  final excluded = {for (final w in exclude) w.trim().toLowerCase()};
  final items = <Map<String, dynamic>>[];
  for (final l in labels) {
    if (l.confidence < minConfidence) continue;
    final word = l.label.trim().toLowerCase().replaceAll('_', ' ');
    if (word.isEmpty || excluded.contains(word)) continue;
    items.add({
      'label': word,
      'visualConfidence': l.confidence,
      'usefulness': 0.5,
      'evidence': '手機辨識：整張照片',
    });
  }
  final parsed = parseCandidates(items, lexicon: lexicon, focus: focus);
  final words = pack ?? LexiconPack.instance;
  final known = [
    for (final c in parsed)
      if (c.levelSource != 'ai' || words.lookup(c.word, pos: c.pos) != null) c,
  ];
  final target = levelIndex(level);
  double score(WordCandidate c) =>
      c.visualConfidence * (1 - 0.12 * (levelIndex(c.level) - target).abs());
  known.sort((a, b) => score(b).compareTo(score(a)));
  final kept = known.take(maxCandidates).toList();
  return [
    for (final (i, c) in kept.indexed)
      c.copyWith(point: spreadPoint(i, kept.length)),
  ];
}

/// [PhotoTagger] that never leaves the phone. `enrich` has no local
/// answer: word data comes from the bundled pack (WordEnricher).
class LocalVisionTagger implements PhotoTagger {
  static const maxCandidates = 24;
  static const minConfidence = 0.1;
  static const modelName = 'Apple Vision（本機）';

  const LocalVisionTagger();

  @override
  Future<List<WordCandidate>> candidates(
    Uint8List jpeg, {
    required String level,
    required CefrLexicon lexicon,
    String lang = 'en',
    String native = 'zh-TW',
    String? focus,
    List<String> exclude = const [],
    bool? asWeb,
  }) async {
    final labels = await LocalVision.classify(jpeg);
    return candidatesFromLabels(labels,
        lexicon: lexicon, level: level, focus: focus, exclude: exclude);
  }

  @override
  Future<EnrichResult> enrich({
    required String word,
    String? pos,
    String? meaning,
    String lang = 'en',
    String native = 'zh-TW',
    int examples = 6,
    List<String> translate = const [],
  }) async =>
      throw TaggingApiException('本機辨識不產生字詞資料');

  @override
  Future<TaggerHealth> checkHealth() async =>
      const TaggerHealth(model: modelName, ollama: true, keyOk: true);

  @override
  void close() {}
}

/// Index of [level] in [cefrLevels] (A1 = 0); unknown levels count as B1.
int levelIndex(String level) {
  final i = cefrLevels.indexOf(level.toUpperCase());
  return i < 0 ? 2 : i;
}
