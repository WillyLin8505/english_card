import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

import '../models/word_detail.dart';

/// Loads the word-detail dictionary produced offline by the Python
/// pipeline (`pipeline/build_word_db.py --out assets/word_db.json`,
/// copied into this Flutter project's `assets/`) and serves lookups
/// from memory. There is deliberately no live network call here: per
/// spec section 1 this app has no cloud sync, so word data ships with
/// the app / is refreshed by re-running the pipeline and re-bundling
/// the asset, not fetched per-word at runtime.
class WordDetailService {
  WordDetailService._();

  static final WordDetailService instance = WordDetailService._();

  Map<String, WordDetail>? _byWord;

  bool get isLoaded => _byWord != null;

  Future<void> load({String assetPath = 'assets/word_db.json'}) async {
    if (_byWord != null) return;
    final raw = await rootBundle.loadString(assetPath);
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    _byWord = decoded.map(
      (word, value) => MapEntry(
        word.toLowerCase(),
        WordDetail.fromJson(value as Map<String, dynamic>),
      ),
    );
  }

  /// Returns the bundled detail for [word], or null if the pipeline
  /// hasn't produced an entry for it yet (e.g. a newly recognized word
  /// the pipeline hasn't been re-run for — the UI should treat this as
  /// "still loading / not available offline" per spec's low-pressure
  /// tone, not an error).
  WordDetail? lookup(String word) {
    final map = _byWord;
    if (map == null) {
      throw StateError(
          'WordDetailService.load() must complete before lookup()');
    }
    return map[word.toLowerCase()];
  }
}
