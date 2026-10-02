import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import '../models/word_entry.dart';

/// A word's level after local correction, and where it came from.
class ResolvedLevel {
  final String level;

  /// 'cefr-j' (the bundled list), 'frequency' (word frequency blended
  /// with the model's guess) or 'ai' (the model's guess alone).
  final String source;
  final double? zipf;
  final String? ipa;

  /// The headword found in the list, if the word was a plural or
  /// inflected form ("slices" → "slice").
  final String? lemma;

  const ResolvedLevel(this.level, this.source,
      {this.zipf, this.ipa, this.lemma});
}

/// The app's local vocabulary database for CEFR (spec section 3: "CEFR
/// 優先由本機詞彙資料庫校正，不完全信任視覺模型自評"): the CEFR-J
/// Wordlist (A1–B2) and Octanove C1/C2 list, with wordfreq frequencies
/// and CMUdict IPA — built by `pipeline/build_cefr_list.py` into
/// `assets/cefr_en.json`. English only; other learning languages fall
/// back to frequency and the model's estimate.
class CefrLexicon {
  final Map<String, (double?, Map<String, String>, String?)> _words;

  CefrLexicon(this._words);

  static CefrLexicon empty() => CefrLexicon(const {});

  static CefrLexicon? _instance;
  static CefrLexicon get instance => _instance ?? empty();

  /// Without the list the app still works: levels then come from word
  /// frequency and the model.
  static Future<CefrLexicon> load(
      {String asset = 'assets/cefr_en.json'}) async {
    if (_instance != null) return _instance!;
    try {
      final raw = jsonDecode(await rootBundle.loadString(asset))
          as Map<String, dynamic>;
      return _instance = CefrLexicon.fromJson(raw);
    } catch (e) {
      debugPrint('CEFR word list unavailable ($asset): $e');
      return _instance = empty();
    }
  }

  factory CefrLexicon.fromJson(Map<String, dynamic> raw) {
    final words = <String, (double?, Map<String, String>, String?)>{};
    for (final e in (raw['words'] as Map<String, dynamic>).entries) {
      final v = e.value as List;
      words[e.key] = (
        (v[0] as num?)?.toDouble(),
        (v[1] as Map).cast<String, String>(),
        v.length > 2 ? v[2] as String? : null,
      );
    }
    return CefrLexicon(words);
  }

  bool get isEmpty => _words.isEmpty;

  static const _stopWords = {
    'a',
    'an',
    'the',
    'on',
    'in',
    'at',
    'of',
    'to',
    'with',
    'for',
    'and',
    'or',
    'up',
    'down',
    'out',
    'off',
    'over',
    'under',
    'by',
    'from',
    'into',
    'onto',
    'some',
    'his',
    'her',
    'my',
    'your',
    'their',
    'its',
    'our',
    'next',
  };

  /// Irregular plurals and verb forms the model returns instead of the
  /// dictionary form (spec 08: App 再做詞形正規化). Ambiguous ones (left,
  /// found, lay) are not listed.
  static const _irregular = <String, (String, String)>{
    'children': ('child', 'noun'), 'men': ('man', 'noun'),
    'women': ('woman', 'noun'), 'people': ('person', 'noun'),
    'feet': ('foot', 'noun'), 'teeth': ('tooth', 'noun'),
    'mice': ('mouse', 'noun'), 'geese': ('goose', 'noun'),
    'leaves': ('leaf', 'noun'), 'knives': ('knife', 'noun'),
    'shelves': ('shelf', 'noun'), 'loaves': ('loaf', 'noun'),
    'eaten': ('eat', 'verb'), 'ate': ('eat', 'verb'),
    'written': ('write', 'verb'), 'wrote': ('write', 'verb'),
    'taken': ('take', 'verb'), 'took': ('take', 'verb'),
    'given': ('give', 'verb'), 'gave': ('give', 'verb'),
    'seen': ('see', 'verb'), 'saw': ('see', 'verb'),
    'gone': ('go', 'verb'), 'went': ('go', 'verb'),
    'done': ('do', 'verb'), 'did': ('do', 'verb'),
    'broken': ('break', 'verb'), 'broke': ('break', 'verb'),
    'fallen': ('fall', 'verb'), 'fell': ('fall', 'verb'),
    'drawn': ('draw', 'verb'), 'drew': ('draw', 'verb'),
    'driven': ('drive', 'verb'), 'drove': ('drive', 'verb'),
    'ridden': ('ride', 'verb'), 'rode': ('ride', 'verb'),
    'worn': ('wear', 'verb'), 'wore': ('wear', 'verb'),
    'frozen': ('freeze', 'verb'), 'froze': ('freeze', 'verb'),
    'spoken': ('speak', 'verb'), 'spoke': ('speak', 'verb'),
    'chosen': ('choose', 'verb'), 'hidden': ('hide', 'verb'),
    'shaken': ('shake', 'verb'), 'shook': ('shake', 'verb'),
    'grown': ('grow', 'verb'), 'grew': ('grow', 'verb'),
    'thrown': ('throw', 'verb'), 'threw': ('throw', 'verb'),
    'flown': ('fly', 'verb'), 'flew': ('fly', 'verb'),
    'blown': ('blow', 'verb'), 'blew': ('blow', 'verb'),
    'sung': ('sing', 'verb'), 'sang': ('sing', 'verb'),
    'swum': ('swim', 'verb'), 'swam': ('swim', 'verb'),
    'began': ('begin', 'verb'), 'begun': ('begin', 'verb'),
    'ran': ('run', 'verb'), 'sat': ('sit', 'verb'), 'stood': ('stand', 'verb'),
    'held': ('hold', 'verb'), 'built': ('build', 'verb'), 'sent': ('send', 'verb'),
    'spent': ('spend', 'verb'), 'slept': ('sleep', 'verb'), 'kept': ('keep', 'verb'),
    'made': ('make', 'verb'), 'bought': ('buy', 'verb'), 'brought': ('bring', 'verb'),
    'caught': ('catch', 'verb'), 'taught': ('teach', 'verb'), 'thought': ('think', 'verb'),
    'sold': ('sell', 'verb'), 'told': ('tell', 'verb'), 'hung': ('hang', 'verb'),
    'fed': ('feed', 'verb'), 'met': ('meet', 'verb'), 'paid': ('pay', 'verb'),
    'said': ('say', 'verb'), 'dug': ('dig', 'verb'), 'stuck': ('stick', 'verb'),
    'swept': ('sweep', 'verb'), 'woke': ('wake', 'verb'), 'woken': ('wake', 'verb'),
  };

  /// The list's entry for [word]; plural nouns and inflected verbs are
  /// looked up by their dictionary form ("slices" → "slice", "sitting" →
  /// "sit", "eaten" → "eat"). A verb whose exact spelling is listed only
  /// as another part of speech is read as the verb ("standing" (v.) →
  /// "stand", not the noun "standing"). Other parts of speech must match
  /// exactly — "steaming" (adj.) is not "steam" (noun).
  (String, (double?, Map<String, String>, String?))? _find(String word,
      [String? pos]) {
    final hit = _words[word];
    final noun = pos == null || pos == 'noun';
    final verb = pos == null || pos == 'verb';
    if (hit != null && !(pos == 'verb' && !hit.$2.containsKey('verb'))) {
      return (word, hit);
    }
    final irregular = _irregular[word];
    if (irregular != null &&
        ((irregular.$2 == 'noun' && noun) || (irregular.$2 == 'verb' && verb))) {
      final h = _words[irregular.$1];
      if (h != null) return (irregular.$1, h);
    }
    String undouble(String stem) => stem.length > 2 &&
            stem[stem.length - 1] == stem[stem.length - 2] &&
            !'aeiouslz'.contains(stem[stem.length - 1])
        ? stem.substring(0, stem.length - 1)
        : stem;
    String cut(int n) => word.substring(0, word.length - n);
    final tries = <String>[
      if (noun && word.endsWith('ies')) '${cut(3)}y',
      if (noun && word.endsWith('es')) cut(2),
      if (noun && word.endsWith('s')) cut(1),
      if (verb && word.endsWith('ied')) '${cut(3)}y',
      if (verb && word.endsWith('ed')) cut(2),
      if (verb && word.endsWith('ed')) cut(1),
      if (verb && word.endsWith('ed')) undouble(cut(2)),
      if (verb && word.endsWith('ing')) cut(3),
      if (verb && word.endsWith('ing')) '${cut(3)}e',
      if (verb && word.endsWith('ing')) undouble(cut(3)),
    ];
    for (final t in tries) {
      final h = _words[t];
      if (h != null && (pos != 'verb' || h.$2.containsKey('verb'))) {
        return (t, h);
      }
    }
    // No verb reading: the exact spelling as whatever it is listed as.
    return hit == null ? null : (word, hit);
  }

  String? ipaOf(String word) {
    final hit = _find(word, 'exact');
    if (hit != null && hit.$1 == word) return hit.$2.$3;
    final parts = word.split(' ');
    if (parts.length < 2) return null;
    final ipas = [for (final p in parts) _words[p]?.$3];
    if (ipas.any((i) => i == null)) return null;
    return '/${ipas.map((i) => i!.replaceAll('/', '')).join(' ')}/';
  }

  /// Level from word frequency alone (Zipf): common words are easier.
  static String levelFromZipf(double zipf) {
    if (zipf >= 5.2) return 'A1';
    if (zipf >= 4.6) return 'A2';
    if (zipf >= 4.0) return 'B1';
    if (zipf >= 3.4) return 'B2';
    if (zipf >= 2.8) return 'C1';
    return 'C2';
  }

  /// The level for [word] used as [pos]: the list's level for that part
  /// of speech (else its lowest); for a phrase, its hardest listed
  /// content word; otherwise frequency blended with [modelLevel]; else
  /// [modelLevel]; else B1.
  ResolvedLevel resolve(String word, String pos,
      {String? modelLevel, double? zipf}) {
    final w = word.trim().toLowerCase();
    final hit = _find(w, w.contains(' ') ? 'phrase' : pos);
    if (hit != null) {
      final (lemma, (freq, byPos, ipa)) = hit;
      final level = byPos[pos] ??
          byPos.values.reduce((a, b) => levelIndex(a) <= levelIndex(b) ? a : b);
      return ResolvedLevel(level, 'cefr-j',
          zipf: zipf ?? freq,
          ipa: lemma == w ? ipa : null,
          lemma: lemma == w ? null : lemma);
    }
    final parts = w
        .split(' ')
        .where((p) => p.isNotEmpty && !_stopWords.contains(p))
        .toList();
    if (w.contains(' ') && parts.isNotEmpty) {
      final levels = [for (final p in parts) _find(p)?.$2.$2.values];
      if (levels.every((l) => l != null && l.isNotEmpty)) {
        final hardest = levels
            .map((ls) =>
                ls!.reduce((a, b) => levelIndex(a) <= levelIndex(b) ? a : b))
            .reduce((a, b) => levelIndex(a) >= levelIndex(b) ? a : b);
        return ResolvedLevel(hardest, 'cefr-j', zipf: zipf, ipa: ipaOf(w));
      }
    }
    if (zipf != null && zipf > 0) {
      final byFreq = levelIndex(levelFromZipf(zipf));
      final blended = modelLevel == null
          ? byFreq
          : (0.7 * byFreq + 0.3 * levelIndex(modelLevel)).round();
      return ResolvedLevel(cefrLevels[math.min(blended, 5)], 'frequency',
          zipf: zipf);
    }
    if (modelLevel != null && cefrLevels.contains(modelLevel)) {
      return ResolvedLevel(modelLevel, 'ai');
    }
    return const ResolvedLevel('B1', 'ai');
  }
}

extension CefrLexiconSample on CefrLexicon {
  /// [count] common single words of [level] for the quick vocabulary
  /// check (快速詞彙檢查), picked evenly through the level's list so the
  /// same learner always sees the same words.
  List<String> sample(String level, int count) {
    final words = [
      for (final e in _words.entries)
        if (!e.key.contains(' ') &&
            e.key.length >= 4 &&
            e.value.$2.values.every((l) => l == level) &&
            (e.value.$1 ?? 0) >= 2.5)
          e.key,
    ]..sort();
    if (words.length <= count) return words;
    final step = words.length / count;
    return [
      for (var i = 0; i < count; i++) words[(i * step + step / 2).floor()]
    ];
  }
}
