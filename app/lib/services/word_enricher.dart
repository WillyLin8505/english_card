import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../models/word_entry.dart';
import 'app_settings.dart';
import 'cefr_lexicon.dart';
import 'lexicon_pack.dart';
import 'photo_intake.dart';
import 'tagging_queue.dart';
import 'word_database_repository.dart';

/// Fetches each new word's full data in the background (spec section 7:
/// 照片辨識後一次取得並保存完整單字資料。主要資料取得後即可顯示，缺少欄位在
/// 背景重試). Local data first — the bundled dictionary and CMUdict IPA —
/// then records exactly which fields are absent. The vision model is never
/// asked to write meanings, definitions, pronunciation, examples or
/// translations; those fields must be present in the downloaded dictionary.
class WordEnricher extends ChangeNotifier {
  static const minExamples = 3;
  static const maxAttempts = 1;

  final WordDatabaseRepository Function() repository;
  final AppSettings settings;
  final PhotoIntake intake;
  final CefrLexicon Function() lexicon;

  /// Photo tagging goes first; the model is shared.
  final TaggingQueue? queue;
  final Duration retryEvery;

  WordEnricher({
    required this.repository,
    required this.settings,
    required this.intake,
    required this.lexicon,
    this.queue,
    this.retryEvery = const Duration(minutes: 1),
  });

  Timer? _timer;
  bool _running = false;
  String? _current;

  String? get current => _current;

  void start() {
    _timer ??= Timer.periodic(retryEvery, (_) => process());
    settings.addListener(_kick);
    queue?.addListener(_kick);
    unawaited(process());
  }

  void _kick() {
    if (queue?.current == null) unawaited(process());
  }

  @override
  void dispose() {
    _timer?.cancel();
    settings.removeListener(_kick);
    queue?.removeListener(_kick);
    super.dispose();
  }

  /// Only unfinished records are checked here. A completed dictionary
  /// record may legitimately have fewer than the target number of examples;
  /// the build backend reports that coverage gap and the App uses what exists.
  List<WordEntry> _needing(WordDatabaseRepository repo) => [
        for (final e in repo.entries)
          if (e.dataStatus != WordDataStatus.complete ||
              e.nativeOfData != settings.nativeLanguage)
            e,
      ];

  /// Failed words wait 2, 4, 8… minutes between attempts.
  bool _due(WordEntry e, DateTime now) {
    if (e.dataStatus != WordDataStatus.failed) return true;
    if (e.dataAttempts >= maxAttempts) return false;
    final wait = Duration(minutes: math.pow(2, e.dataAttempts).toInt());
    return now.difference(e.updatedAt) >= wait;
  }

  Future<void> process() async {
    if (_running) return;
    _running = true;
    try {
      final pack = LexiconPack.instance;
      if (pack.target == repository().language &&
          pack.native == settings.nativeLanguage) {
        repository().linkLexicon(pack);
      }
      while (queue?.current == null) {
        final repo = repository();
        final now = repo.clock();
        final next = _needing(repo).where((e) => _due(e, now)).firstOrNull;
        if (next == null) break;
        final ok = await enrich(repo, next);
        if (!ok) break;
      }
    } finally {
      _running = false;
      _current = null;
      notifyListeners();
    }
  }

  /// Verifies the data already loaded from the offline dictionary.
  Future<bool> enrich(WordDatabaseRepository repo, WordEntry e) async {
    _current = e.id;
    notifyListeners();
    final native = settings.nativeLanguage;
    final retranslate = e.nativeOfData != native;
    final localIpa =
        e.ipa == null && repo.language == 'en' ? lexicon().ipaOf(e.word) : null;
    final untranslated = [
      for (final (i, x) in e.examples.indexed)
        if (retranslate || (x.translation ?? '').isEmpty) (i, x.text),
    ];
    final needExamples = math.max(0, minExamples - e.examples.length);
    final missingData = retranslate ||
        needExamples > 0 ||
        untranslated.isNotEmpty ||
        e.meaning.isEmpty ||
        e.definition == null ||
        (e.ipa == null && localIpa == null);
    if (!missingData) {
      repo.applyWordData(e.id,
          ipa: localIpa,
          ipaSource: 'cmudict',
          translatedFor: native,
          status: WordDataStatus.complete);
      return true;
    }
    final missing = <String>[
      if (e.meaning.isEmpty || retranslate) '母語釋義',
      if (e.definition == null || retranslate) '定義',
      if (e.ipa == null && localIpa == null) '發音',
      if (needExamples > 0) '例句（缺 $needExamples）',
      if (untranslated.isNotEmpty || retranslate) '例句翻譯',
    ];
    repo.applyWordData(e.id,
        ipa: localIpa,
        ipaSource: localIpa == null ? null : 'cmudict',
        status: WordDataStatus.failed,
        error: '離線字庫缺少：${missing.join('、')}');
    return true;
  }
}
