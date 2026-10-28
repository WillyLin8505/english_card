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

/// One word the text recognizer read, and where it is printed.
typedef TextWord = ({String text, LabelBox box});

/// One line of printed text on a photo (a sign, a menu row, a line of a
/// book page). [words] are the recognizer's own word boxes when it gives
/// them; otherwise [wordsOf] splits the line's box by letters.
class TextLine {
  final String text;
  final LabelBox box;
  final double confidence;
  final List<TextWord> words;

  const TextLine(this.text, this.box,
      {this.confidence = 1, this.words = const []});

  /// `{text, confidence, box: [x, y, w, h], words: [{text, box}]}`, all
  /// boxes normalized (0–1) with the origin at the top left.
  static TextLine? fromMap(Object? raw) {
    if (raw is! Map || raw['text'] is! String) return null;
    final box = _box(raw['box']);
    if (box == null) return null;
    return TextLine(
      raw['text'] as String,
      box,
      confidence: (raw['confidence'] as num?)?.toDouble() ?? 1,
      words: [
        for (final w in (raw['words'] as List? ?? const []))
          if (w is Map && w['text'] is String && _box(w['box']) != null)
            (text: w['text'] as String, box: _box(w['box'])!),
      ],
    );
  }

  static LabelBox? _box(Object? v) {
    if (v is! List || v.length < 4 || v.any((n) => n is! num)) return null;
    double c(Object? n) => (n as num).toDouble().clamp(0.0, 1.0);
    return LabelBox(c(v[0]), c(v[1]), c(v[2]), c(v[3]));
  }
}

/// On-device text recognition (問題回報 #324: 拍文字擷取單字). iOS reads
/// text with Apple Vision (`VNRecognizeTextRequest`), Android with ML Kit's
/// bundled Latin model, both on the `photo_english/text_recognition`
/// channel (`ios/Runner/AppDelegate.swift`, `MainActivity.kt`). Nothing
/// leaves the phone. The web build has no recognizer and says so.
class TextScan {
  static const channel = MethodChannel('photo_english/text_recognition');

  /// Whether this device can read text; set at start-up from [probe].
  static bool available = false;

  /// Replaces the platform channel: tests and other front ends.
  static Future<List<TextLine>> Function(Uint8List jpeg)? recognizer;

  static const unavailableMessage = '網頁版還不能找照片裡的文字，請用手機 App';

  /// Shown when the phone's text reader fails; the platform's own English
  /// error is for developers, not the learner (問題回報 #377).
  static const readFailedMessage = '手機暫時無法讀取這張照片裡的文字，請換一張照片再試';

  static Future<bool> probe() async {
    if (recognizer != null) return true;
    if (kIsWeb) return false;
    try {
      return await channel.invokeMethod<bool>('available') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static Future<List<TextLine>> recognize(Uint8List jpeg) async {
    final custom = recognizer;
    if (custom != null) return custom(jpeg);
    if (kIsWeb) throw TaggingApiException(unavailableMessage);
    final List<Object?>? raw;
    try {
      raw =
          await channel.invokeListMethod<Object?>('recognize', {'image': jpeg});
    } on PlatformException catch (e) {
      debugPrint('text recognition failed: ${e.code} ${e.message}');
      throw TaggingApiException(readFailedMessage);
    } on MissingPluginException {
      throw TaggingApiException('這台裝置不能讀取照片裡的文字');
    }
    return [
      for (final item in raw ?? const [])
        if (TextLine.fromMap(item) case final line?) line,
    ];
  }
}

final _token = RegExp(r"[A-Za-z]+(?:['’][A-Za-z]+)*");

/// [line]'s words with their boxes: the recognizer's when given, else
/// cut from the line's box in proportion to where each word starts.
List<TextWord> wordsOf(TextLine line) {
  if (line.words.isNotEmpty) {
    return [
      for (final w in line.words)
        for (final m in _token.allMatches(w.text)) (text: m[0]!, box: w.box),
    ];
  }
  final n = line.text.length;
  if (n == 0) return const [];
  final b = line.box;
  return [
    for (final m in _token.allMatches(line.text))
      (
        text: m[0]!,
        box: LabelBox(b.left + b.width * m.start / n, b.top,
            b.width * (m.end - m.start) / n, b.height),
      ),
  ];
}

/// Function words that are never worth a card, whatever their level.
const textStopWords = {
  'a',
  'an',
  'the',
  'and',
  'or',
  'but',
  'nor',
  'so',
  'yet',
  'if',
  'than',
  'then',
  'that',
  'this',
  'these',
  'those',
  'there',
  'here',
  'what',
  'which',
  'who',
  'whom',
  'whose',
  'when',
  'where',
  'why',
  'how',
  'i',
  'me',
  'my',
  'mine',
  'you',
  'your',
  'yours',
  'he',
  'him',
  'his',
  'she',
  'her',
  'hers',
  'it',
  'its',
  'we',
  'us',
  'our',
  'ours',
  'they',
  'them',
  'their',
  'theirs',
  'myself',
  'yourself',
  'itself',
  'be',
  'am',
  'is',
  'are',
  'was',
  'were',
  'been',
  'being',
  'have',
  'has',
  'had',
  'do',
  'does',
  'did',
  'will',
  'would',
  'shall',
  'should',
  'can',
  'could',
  'may',
  'might',
  'must',
  'not',
  'no',
  'yes',
  'of',
  'to',
  'in',
  'on',
  'at',
  'by',
  'for',
  'with',
  'from',
  'into',
  'onto',
  'about',
  'as',
  'up',
  'out',
  'off',
  'over',
  'under',
  'per',
  'via',
  'all',
  'any',
  'some',
  'each',
  'every',
  'both',
  'few',
  'more',
  'most',
  'much',
  'many',
  'such',
  'own',
  'same',
  'other',
  'very',
  'too',
  'also',
  'just',
  'only',
  'ok',
  'okay',
  'etc',
  'vs',
  'mr',
  'mrs',
  'ms',
  'dr',
  'st',
  'co',
  'inc',
  'ltd',
  'www',
  'com',
  'oh',
  'hey',
  'hi',
};

/// Parts of speech in the CEFR list that are function words.
const _functionPos = {
  'pronoun',
  'preposition',
  'determiner',
  'conjunction',
  'number',
  'interjection',
  'infinitive-to',
};

/// First names that are also ordinary words. Written with a capital in
/// running text (not a title-case sign), they are read as names.
const _nameWords = {
  'will',
  'mark',
  'rose',
  'bill',
  'jack',
  'grace',
  'hope',
  'joy',
  'may',
  'june',
  'april',
  'frank',
  'pat',
  'sue',
  'rob',
  'art',
  'ray',
  'dawn',
  'amber',
  'iris',
  'lily',
  'ruby',
  'victor',
  'faith',
  'violet',
  'summer',
  'max',
  'drew',
  'gene',
  'chase',
  'hunter',
  'pearl',
  'penny',
  'sandy',
  'holly',
  'ivy',
  'daisy',
  'robin',
  'river',
  'sky',
  'august',
  'earnest',
};

/// A word read off a photo, in dictionary form.
typedef TextLemma = ({String lemma, String pos, LexEntry? entry});

/// [token]'s dictionary form, through the language pack's forms table
/// first (menus → menu, served → serve), then the CEFR list's rules.
/// Null for function words, numbers and words neither knows — brand
/// names, places, OCR misreads.
TextLemma? textLemma(String token,
    {required CefrLexicon lexicon, LexiconPack? pack}) {
  var w = LexiconPack.normalize(token);
  if (w.endsWith("'s")) w = w.substring(0, w.length - 2);
  if (w.length < 2 || !RegExp(r'^[a-z]+$').hasMatch(w)) return null;
  if (textStopWords.contains(w)) return null;
  final words = pack ?? LexiconPack.instance;
  final hit = words.lookup(w);
  if (hit != null) {
    final e = hit.entry;
    if (_functionPos.contains(e.pos) || textStopWords.contains(e.normalized)) {
      return null;
    }
    return (lemma: e.normalized, pos: shortPos(e.pos), entry: e);
  }
  final listed = lexicon.lemmaOf(w);
  if (listed == null || listed.pos.isEmpty) return null;
  final pos = listed.pos.first;
  if (_functionPos.contains(pos) || textStopWords.contains(listed.lemma)) {
    return null;
  }
  return (lemma: listed.lemma, pos: shortPos(pos), entry: null);
}

/// Whether [token] (as written in [words] at [index]) reads as a
/// person's name: a capitalized name-word in running text — not at the
/// start of a sentence and not on a title-case sign or menu heading,
/// where every word has a capital anyway.
bool looksLikeName(List<String> words, int index) {
  final t = words[index];
  if (!_nameWords.contains(t.toLowerCase())) return false;
  if (t.isEmpty || t[0] != t[0].toUpperCase() || t == t.toUpperCase()) {
    return false;
  }
  final capitals = words.where((w) => w[0] == w[0].toUpperCase()).length;
  if (words.length > 1 && capitals / words.length >= 0.6) return false;
  return index > 0;
}

/// Text read off a photo → vocabulary candidates (問題回報 #324): English
/// words in dictionary form, without function words, names and words the
/// dictionaries lack, kept around the learner's [level] (much easier words
/// are already known), each with the box where it is printed. One word
/// printed several times counts once, in its largest spot.
List<WordCandidate> candidatesFromText(
  List<TextLine> lines, {
  required CefrLexicon lexicon,
  required String level,
  LexiconPack? pack,
  List<String> exclude = const [],
  int maxCandidates = TextScanTagger.maxCandidates,
}) {
  final excluded = {for (final w in exclude) w.trim().toLowerCase()};
  final target = levelIndex(level);
  final found = <String,
      ({
    TextLemma lemma,
    LabelBox box,
    String line,
    double confidence,
    int count
  })>{};
  for (final line in lines) {
    final words = wordsOf(line);
    final spelled = [for (final w in words) w.text];
    for (final (i, w) in words.indexed) {
      if (looksLikeName(spelled, i)) continue;
      final l = textLemma(w.text, lexicon: lexicon, pack: pack);
      if (l == null || excluded.contains(l.lemma)) continue;
      final key = '${l.lemma}|${l.pos}';
      final had = found[key];
      final bigger = had == null || w.box.height > had.box.height;
      found[key] = (
        lemma: l,
        box: bigger ? w.box : had.box,
        line: bigger ? line.text : had.line,
        confidence: math.max(line.confidence, had?.confidence ?? 0),
        count: (had?.count ?? 0) + 1,
      );
    }
  }
  final out = <(WordCandidate, double)>[];
  for (final f in found.values) {
    final e = f.lemma.entry;
    final resolved = lexicon.resolve(f.lemma.lemma, f.lemma.pos,
        modelLevel: e?.cefr, zipf: e?.zipf);
    final wordLevel = e?.cefr != null && cefrLevels.contains(e!.cefr)
        ? e.cefr!
        : resolved.level;
    final gap = levelIndex(wordLevel) - target;
    // Two levels below the learner is already known; the dial can still
    // reach one level down.
    if (gap < -1 && target > 0) continue;
    final fit = switch (gap) { 0 || 1 => 1.0, 2 => 0.75, -1 => 0.6, _ => 0.4 };
    // Big print (a sign's headline) and repeated words matter more.
    final salience =
        (f.box.height * 8).clamp(0.0, 1.0) * 0.5 + math.min(f.count - 1, 3) / 6;
    final line = f.line.length > 40 ? '${f.line.substring(0, 40)}…' : f.line;
    out.add((
      WordCandidate(
        word: f.lemma.lemma,
        lemma: f.lemma.lemma,
        pos: f.lemma.pos,
        meaning: e?.learnerMeaning ?? '',
        level: wordLevel,
        levelSource: e?.cefr != null ? 'cefr-j' : resolved.source,
        zipf: e?.zipf ?? resolved.zipf,
        ipa: e?.ipa ?? resolved.ipa,
        evidence: '照片文字：「$line」',
        point: f.box.center,
        box: f.box,
        visualConfidence: f.confidence.clamp(0.5, 1.0),
        usefulness: (0.4 + salience).clamp(0.0, 1.0),
        lexemeId: e?.id,
      ),
      fit + salience,
    ));
  }
  out.sort((a, b) => b.$2.compareTo(a.$2));
  return [for (final (c, _) in out.take(maxCandidates)) c];
}

/// [PhotoTagger] that reads the photo's printed text on the device.
class TextScanTagger implements PhotoTagger {
  static const maxCandidates = 24;
  static const modelName = '手機文字辨識（本機）';

  const TextScanTagger();

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
    final lines = await TextScan.recognize(jpeg);
    return candidatesFromText(lines,
        lexicon: lexicon, level: level, exclude: exclude);
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
      throw TaggingApiException('文字辨識不產生字詞資料');

  @override
  Future<TaggerHealth> checkHealth() async =>
      const TaggerHealth(model: modelName, ollama: true, keyOk: true);

  @override
  void close() {}
}
