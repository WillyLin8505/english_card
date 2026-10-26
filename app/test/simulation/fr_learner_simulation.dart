// An English speaker learning French (問題回報 #363; not part of the regular suite).
//
// The French pack (serve_app /api/lexicon?target=fr&native=en) is loaded
// directly, with learningLanguage fr and nativeLanguage en, because the app
// does not offer French as a learning language yet. A learner at SIM_LEVEL
// goes through: 新手引導 (as far as it lets them), the review front/back of
// SIM_WORDS words, their 單字詳情 pages, and every tab. Every screen's text
// is written to SIM_OUT, plus per-word checks a French learner cares about:
// the noun's article/gender, the verb's conjugation, the English meaning,
// French pronunciation (audio or fr TTS), and Chinese leaking into the
// English interface. Fails only on layout errors and "null" on screen; the
// learner findings are for the reviewer (run_round.py --lang fr).
//
//   flutter test test/simulation/fr_learner_simulation.dart
//   SIM_PACK (fr→en /api/lexicon JSON)  SIM_WORDS (40)  SIM_LEVEL (A2)
//   SIM_SEED (1)  SIM_OUT (build/fr_learner.json)
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';
import 'learner_view_simulation.dart' show screenTexts;

String _opt(String k, String d) => Platform.environment[k] ?? d;

const _levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
String _en(String zh) => translateUi(zh, 'en');

/// Chinese characters in an English interface.
final _cjk = RegExp(r'[一-鿿]');
final _leakedNull = RegExp(r'^null$|[：:]\s*null$|^null\s*[：:]');
final _gender = RegExp(r'\b(masculine|feminine|masc\.|fem\.|m\.|f\.|nm|nf)\b',
    caseSensitive: false);

Future<void> capture(WidgetTester tester, String name) async {
  if (_opt('SIM_CAPTURE', '0') != '1') return;
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(
        find.byType(RepaintBoundary).first);
    final image = await boundary.toImage(pixelRatio: 0.5);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    File('${File(_opt('SIM_OUT', 'build/fr_learner.json')).parent.path}/fr_$name.png')
        .writeAsBytesSync(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

class _RecordingSpeaker implements Speaker {
  final calls = <Map<String, String?>>[];
  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    calls.add({'text': text, 'language': language, 'audio': audioUrl});
    return true;
  }

  @override
  Future<void> stop() async {}
}

void main() {
  testWidgets('an English speaker learns French', (tester) async {
    if (_opt('SIM_CAPTURE', '0') == '1') {
      await tester.runAsync(() async {
        final font = File(_opt('SIM_FONT', 'C:/Windows/Fonts/msjh.ttc'));
        if (font.existsSync()) {
          final bytes = ByteData.sublistView(font.readAsBytesSync());
          for (final family in ['Ahem', 'Manrope', 'Inter', 'Roboto']) {
            await (FontLoader(family)..addFont(Future.value(bytes))).load();
          }
        }
      });
    }
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(
              File(_opt('SIM_PACK', 'build/fr_pack.json')).readAsStringSync())
          as Map<String, dynamic>);
    final level = _opt('SIM_LEVEL', 'A2');
    final want = int.parse(_opt('SIM_WORDS', '40'));
    final rnd = Random(int.parse(_opt('SIM_SEED', '1')));
    final errors = <String>[];
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) {
      // Where an overflow happens: the widget's source line.
      final at =
          RegExp(r'lib/(\S+?\.dart:\d+)').firstMatch(d.toString())?.group(1);
      errors.add(
          '$current：${d.exceptionAsString().split('\n').first}${at == null ? '' : ' ($at)'}');
    };
    addTearDown(() => FlutterError.onError = original);
    Future<void> settleUp() => tester.pumpAndSettle(
        const Duration(milliseconds: 100),
        EnginePhase.sendSemanticsUpdate,
        const Duration(seconds: 10));

    // 1. 新手引導, the way an English speaker wanting French would try it.
    final onboarding = <String, Object?>{
      'fr_learning_available': learningLanguageAvailable('fr'),
      'en_native_available': nativeLanguageAvailable('en'),
    };
    current = 'onboarding';
    OnboardingResult? result;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
        home: OnboardingScreen(
            lexicon: testLexicon(), onDone: (r) => result = r)));
    await settleUp();
    onboarding['step1'] = screenTexts(tester);
    final frOption = find.textContaining('法文（Français）');
    if (frOption.evaluate().isNotEmpty) {
      await tester.tap(frOption.first, warnIfMissed: false);
      await settleUp();
    }
    final enOption = find.textContaining('英文（English）');
    if (enOption.evaluate().length > 1) {
      await tester.tap(enOption.last, warnIfMissed: false);
      await settleUp();
    }
    onboarding['step1_after_choosing'] = screenTexts(tester);
    for (final next in ['下一步', _en('下一步')]) {
      if (find.text(next).evaluate().isNotEmpty) {
        await tester.tap(find.text(next));
        await settleUp();
        break;
      }
    }
    onboarding['step2'] = screenTexts(tester);
    for (final pick in ['會基礎單字', _en('會基礎單字')]) {
      if (find.text(pick).evaluate().isNotEmpty) {
        await tester.tap(find.text(pick));
        await settleUp();
        break;
      }
    }
    onboarding['step2_after_choosing'] = screenTexts(tester);
    for (final go in ['開始使用', _en('開始使用')]) {
      if (find.text(go).evaluate().isNotEmpty) {
        await tester.tap(find.text(go).last, warnIfMissed: false);
        await settleUp();
        break;
      }
    }
    onboarding['step3'] = screenTexts(tester);
    onboarding['result'] = result == null
        ? null
        : {
            'learning': result!.learningLanguage,
            'native': result!.nativeLanguage,
            'level': result!.level,
            'source': result!.source
          };

    // 2. 複習: French words around the learner's level, English interface.
    final li = _levels.indexOf(level);
    final near = pack.catalogWords
        .where((w) =>
            w.full &&
            w.cefr != null &&
            (_levels.indexOf(w.cefr!) - li).abs() <= 1)
        .toList()
      ..shuffle(rnd);
    final repo = WordDatabaseRepository(
        language: 'fr',
        clock: () => testNow,
        profile: UserVocabularyProfile.start(level, now: testNow));
    final posOf = <String, String>{};
    void fill() {
      for (final w in near) {
        if (repo.entries.length >= want) break;
        if (posOf.containsKey(w.lemma)) continue;
        try {
          repo.addWord(
              word: w.lemma,
              pos: shortPos(w.pos),
              meaning: w.learnerMeaning ?? '',
              level: w.cefr);
          posOf[w.lemma] = w.pos;
        } on DuplicateWordException {
          continue;
        }
      }
    }

    fill();
    repo.linkLexicon(pack);
    // linkLexicon merges a learner word into its canonical headword when both
    // are saved (assis→asseoir, 問題回報 #710): the collection shrinks, so top
    // it up with words not yet tried and link again. The count check stays exact.
    for (var round = 0; round < 3 && repo.entries.length < want; round++) {
      fill();
      repo.linkLexicon(pack);
    }
    final settings =
        AppSettings.inMemory(learningLanguage: 'fr', nativeLanguage: 'en');
    final speaker = _RecordingSpeaker();
    final words = <String, Map<String, dynamic>>{};
    final app = await pumpApp(tester,
        initialTab: AppTab.review,
        repository: repo,
        settings: settings,
        speaker: speaker,
        size: const Size(390, 844));
    await settleUp();
    final tabs = <String, List<String>>{'review_start': screenTexts(tester)};
    current = 'review start';
    if (await startReview(tester, label: _en)) {
      await settleUp();
    } else {
      errors.add('review: no "${_en('綜合')}" / "${_en('開始複習')}" button');
    }
    var n = 0;
    while (find.byType(FlashcardFront).evaluate().isNotEmpty && n < want * 2) {
      final front = tester.widget<FlashcardFront>(find.byType(FlashcardFront));
      final word = front.entry.word;
      final w = words.putIfAbsent(word,
          () => {'word': word, 'level': front.entry.level, 'pos': posOf[word]});
      try {
        current = '$word front';
        w['exercise'] = front.session?.exercise?.type.name;
        w['front'] = screenTexts(tester);
        final said = speaker.calls.length;
        final s = front.session;
        if (s != null && !s.canAnswer) {
          s.reportPhotoState(s.photoAttempt, true);
          s.showAnswer();
        } else {
          final show = find.text(_en('顯示答案'));
          if (show.evaluate().isEmpty) throw StateError('no "${_en('顯示答案')}"');
          await tester.tap(show.first);
        }
        await settleUp();
        current = '$word back';
        if (n == 0) await capture(tester, 'review_back');
        final scroll = find.byType(SingleChildScrollView);
        if (scroll.evaluate().isNotEmpty) {
          await tester.drag(scroll.first, const Offset(0, -4000));
          await settleUp();
        }
        w['back'] = screenTexts(tester);
        w['spoken'] = speaker.calls.sublist(said);
        final good = find.text(Rating.good.labelIn('en'));
        if (good.evaluate().isEmpty) {
          throw StateError('no "${Rating.good.labelIn('en')}"');
        }
        await tester.tap(good.first);
        await settleUp();
      } catch (e) {
        errors.add('$current：${e.toString().split('\n').first}');
        break;
      }
      n++;
    }

    // 3. 單字詳情 of the first 15 words.
    for (final e in repo.entries.take(15)) {
      current = '${e.word} detail';
      app.navigator.openWord(e.id);
      await tester.pumpAndSettle();
      if (find.byType(WordDetailScreen).evaluate().isEmpty) {
        errors.add('$current：not opened');
        continue;
      }
      if (e.id == repo.entries.first.id) await capture(tester, 'word_detail');
      final seen = <String>[];
      final scrollable = find.byType(Scrollable);
      for (var k = 0; k < 6; k++) {
        for (final t in screenTexts(tester)) {
          if (!seen.contains(t)) seen.add(t);
        }
        if (scrollable.evaluate().isEmpty) break;
        await tester.drag(scrollable.first, const Offset(0, -700));
        await tester.pumpAndSettle();
      }
      words.putIfAbsent(e.word, () => {'word': e.word})['detail'] = seen;
      Navigator.of(tester.element(find.byType(Scaffold).last)).maybePop();
      await tester.pumpAndSettle();
    }

    // 4. Every tab: 拍照, 相片冊/卡片集, 單字本, 設定.
    for (final tab in [
      AppTab.camera,
      AppTab.album,
      AppTab.words,
      AppTab.settings
    ]) {
      current = 'tab ${tab.name}';
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
      await pumpApp(tester,
          initialTab: tab,
          repository: repo,
          settings: settings,
          speaker: speaker,
          size: const Size(390, 844));
      await settleUp();
      final seen = <String>[];
      final scrollable = find.byType(Scrollable);
      for (var k = 0; k < 5; k++) {
        for (final t in screenTexts(tester)) {
          if (!seen.contains(t)) seen.add(t);
        }
        if (scrollable.evaluate().isEmpty) break;
        await tester.drag(scrollable.first, const Offset(0, -600),
            warnIfMissed: false);
        await settleUp();
      }
      tabs[tab.name] = seen;
    }

    // Learner checks per reviewed word.
    final checks = <String, List<String>>{
      'noun_no_article_or_gender': [],
      'verb_no_conjugation': [],
      'no_english_meaning': [],
      'not_spoken_in_french': [],
      'no_audio_file': [],
    };
    for (final w in words.values) {
      final back = (w['back'] as List<String>? ?? const []);
      if (back.isEmpty) continue;
      final word = w['word'] as String;
      final pos = w['pos'] as String?;
      final lex =
          pack.entriesFor(word).where((e) => e.pos == pos).firstOrNull ??
              pack.entriesFor(word).firstOrNull;
      // The headword itself with its article ("le verre", "un verre") or a
      // gender mark; an example sentence that happens to say "un verre"
      // does not tell the learner the gender of "verre".
      final headword = RegExp(
          "^(le|la|l'|l’|un|une)\\s?${RegExp.escape(word)}\$",
          caseSensitive: false);
      if (pos == 'noun' &&
          !back.any((t) =>
              headword.hasMatch(t.trim()) ||
              _gender.hasMatch(t) && t.length < 40)) {
        checks['noun_no_article_or_gender']!.add(word);
      }
      if (pos == 'verb') {
        final forms =
            lex?.forms.map((f) => f.form).where((f) => f != word).toSet() ?? {};
        if (!back.any((t) => forms.any((f) => t.contains(f)))) {
          checks['verb_no_conjugation']!.add(word);
        }
      }
      final meanings =
          lex?.senses.map((s) => s.native ?? '').where((m) => m.isNotEmpty) ??
              const <String>[];
      if (!back.any((t) => meanings.any(
          (m) => t.contains(m.split(',').first.split('(').first.trim())))) {
        checks['no_english_meaning']!.add(word);
      }
      final spoken =
          (w['spoken'] as List?)?.cast<Map<String, String?>>() ?? const [];
      if (spoken.isEmpty || spoken.any((c) => c['language'] != 'fr')) {
        checks['not_spoken_in_french']!.add(
            '$word (${spoken.map((c) => c['language']).toSet().join('/')})');
      }
      if (spoken.isEmpty || spoken.every((c) => (c['audio'] ?? '').isEmpty)) {
        checks['no_audio_file']!.add(word);
      }
    }
    final leaks = <String, Set<String>>{};
    void scan(String where, Iterable<String> texts) {
      for (final t in texts) {
        if (_cjk.hasMatch(t)) leaks.putIfAbsent(where, () => {}).add(t);
      }
    }

    onboarding.forEach((k, v) {
      if (v is List<String>) scan('onboarding.$k', v);
    });
    tabs.forEach((k, v) => scan('tab.$k', v));
    for (final w in words.values) {
      for (final part in ['front', 'back', 'detail']) {
        scan(part, (w[part] as List<String>? ?? const []));
      }
    }
    final nulls = [
      for (final w in words.values)
        for (final part in ['front', 'back', 'detail'])
          for (final t in (w[part] as List<String>? ?? const <String>[]))
            if (_leakedNull.hasMatch(t.trim())) '${w['word']} $part：$t'
    ];
    final report = {
      'level': level,
      'added': repo.entries.length,
      'reviewed': n,
      'errors': errors.toSet().toList(),
      'nulls': nulls,
      'onboarding': onboarding,
      'checks': {
        for (final e in checks.entries)
          e.key: {'count': e.value.length, 'words': e.value}
      },
      'chinese_in_english_ui': {
        for (final e in leaks.entries) e.key: e.value.toList()
      },
      'tabs': tabs,
      'words': words.values.toList(),
    };
    File(_opt('SIM_OUT', 'build/fr_learner.json'))
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(
        'added ${repo.entries.length}, reviewed $n, ${errors.length} errors, ${nulls.length} nulls, '
        '${checks.entries.map((e) => '${e.key} ${e.value.length}').join(', ')}, '
        'chinese on ${leaks.length} screens');
    FlutterError.onError = original;
    expect(errors, isEmpty);
    expect(nulls, isEmpty);
    expect(repo.entries.length, want);
    expect(words.values.where((w) => w.containsKey('back')).length,
        greaterThanOrEqualTo(want ~/ 2));
  }, timeout: const Timeout(Duration(minutes: 8)));
}
