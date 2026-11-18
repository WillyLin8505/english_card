import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../models/learning_card.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'cefr_lexicon.dart';
import 'lexicon_pack.dart';
import 'local_vision_rules.dart';
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
    if (visionCategoryLabels.contains(word)) continue;
    if (word.contains(' ') &&
        word.split(' ').any(visionQualifierWords.contains)) {
      continue;
    }
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
      // A phrase must be a real entry: `engine vehicle` is a taxonomy tag.
      if ((c.levelSource != 'ai' && !c.word.contains(' ')) ||
          words.lookup(c.word, pos: c.pos) != null)
        c,
  ];
  final target = levelIndex(level);
  double score(WordCandidate c) =>
      c.visualConfidence *
      (1 - 0.12 * (levelIndex(c.level) - target).abs()) *
      (visionWeakLabels.contains(c.word.toLowerCase()) ? visionWeakFactor : 1);
  known.sort((a, b) => score(b).compareTo(score(a)));
  final kept = known.take(maxCandidates).toList();
  return [
    for (final (i, c) in kept.indexed)
      // Fanned out on purpose (no positions from the classifier), so these
      // keep their pins rather than count as whole-picture words (#703).
      c.copyWith(point: spreadPoint(i, kept.length), grounded: true),
  ];
}

/// English classifier label → French words for a learner of French (問題回報
/// #1658, card #1205). Apple Vision only names things in English, so for
/// French the label is looked up in `assets/vision_fr.json`, built offline by
/// `lexicon/tools/card1205_build_vision_fr.py` from Wiktionary glosses
/// (CC BY-SA), Lexique 3.83 frequency and the lexicon's fr_gender — no AI.
class VisionFrench {
  /// english → [[french, level, gender, zipf], …], best first.
  static Map<String, List<List<Object?>>>? labels;

  static Future<void> ensureLoaded() async {
    if (labels != null) return;
    try {
      final raw = await rootBundle.loadString('assets/vision_fr.json');
      final m = (jsonDecode(raw) as Map<String, dynamic>)['labels']
          as Map<String, dynamic>;
      labels = {
        for (final e in m.entries)
          e.key: [for (final x in e.value as List) List<Object?>.from(x as List)]
      };
    } catch (e) {
      debugPrint('vision_fr.json unavailable: $e');
      labels = const {};
    }
  }
}

/// [candidatesFromLabels] for French: each English label that has a French
/// noun becomes that noun (`chaise` for `chair`), levelled by Lexique
/// frequency / the reviewed CEFR list, nudged toward [level].
List<WordCandidate> frenchCandidatesFromLabels(
  List<VisionLabel> labels, {
  required String level,
  Map<String, List<List<Object?>>>? table,
  List<String> exclude = const [],
  int maxCandidates = LocalVisionTagger.maxCandidates,
  double minConfidence = LocalVisionTagger.minConfidence,
}) {
  final map = table ?? VisionFrench.labels ?? const {};
  final excluded = {for (final w in exclude) w.trim().toLowerCase()};
  final seen = <String>{};
  final found = <WordCandidate>[];
  for (final l in labels) {
    if (l.confidence < minConfidence) continue;
    final en = l.label.trim().toLowerCase().replaceAll('_', ' ');
    if (en.isEmpty || visionCategoryLabels.contains(en)) continue;
    if (en.split(' ').any(visionQualifierWords.contains)) continue;
    final hit = map[en];
    if (hit == null || hit.isEmpty) continue;
    final row = hit.first;
    final fr = row[0] as String;
    if (excluded.contains(fr) || !seen.add(fr)) continue;
    found.add(WordCandidate(
      word: fr,
      pos: 'noun',
      meaning: en,
      level: row[1] as String,
      levelSource: 'frequency',
      zipf: (row[3] as num?)?.toDouble(),
      evidence: '手機辨識：整張照片',
      point: const LabelPoint(0.5, 0.5),
      visualConfidence: l.confidence,
    ));
  }
  final target = levelIndex(level);
  double score(WordCandidate c) =>
      c.visualConfidence *
      (1 - 0.12 * (levelIndex(c.level) - target).abs()) *
      (visionWeakLabels.contains(c.meaning) ? visionWeakFactor : 1);
  found.sort((a, b) => score(b).compareTo(score(a)));
  final kept = found.take(maxCandidates).toList();
  return [
    for (final (i, c) in kept.indexed)
      c.copyWith(point: spreadPoint(i, kept.length), grounded: true),
  ];
}

/// [PhotoTagger] that never leaves the phone. `enrich` has no local
/// answer: word data comes from the bundled pack (WordEnricher).
class LocalVisionTagger implements PhotoTagger {
  static const maxCandidates = 24;
  static const minConfidence = 0.03;
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
    if (lang == 'fr') {
      await VisionFrench.ensureLoaded();
      return frenchCandidatesFromLabels(labels,
          level: level, exclude: exclude);
    }
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
