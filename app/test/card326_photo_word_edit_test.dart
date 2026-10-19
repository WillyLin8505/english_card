// 問題回報 #323 / 卡 #326: on 照片詳情 a wrong label can be changed to the
// right word (looked up again, the AI's word kept as 原標籤 and never
// offered again), deleted without counting as 已學會, and a missed word can
// be added — placed with a tap on the photo, or left without a pin. Words
// the pack lacks become missing-word requests (/api/missing).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

WordCandidate _cand(String w, double x, {String pos = 'noun'}) =>
    WordCandidate(
        word: w,
        pos: pos,
        meaning: '$w 的意思',
        level: 'A2',
        levelSource: 'cefr-j',
        evidence: 'e',
        point: LabelPoint(x, .5),
        visualConfidence: .9,
        usefulness: .8);

LexiconPack _pack() => LexiconPack()
  ..loadJson({
    'schema_version': 3,
    'target_language': 'en',
    'native_language': 'zh-TW',
    'lexemes': [
      {
        'id': 7,
        'lemma': 'mug',
        'normalized': 'mug',
        'pos': 'noun',
        'cefr': 'B1',
        'status': 'full',
        'senses': [
          {'id': 71, 'native': '馬克杯', 'definition': 'a large cup'}
        ],
        'forms': [
          {'field': 'form', 'form': 'mugs', 'normalized': 'mugs', 'label': 'plural'}
        ],
      },
    ],
  });

({WordDatabaseRepository repo, LexiconPack pack}) _setup() {
  final repo = WordDatabaseRepository(
      clock: () => testNow,
      profile: UserVocabularyProfile.start('A2', now: testNow));
  repo.addPhoto(Photo(
      id: 'p',
      title: 'p',
      takenAt: testNow,
      createdAt: testNow,
      storedKey: 'p',
      taggingStatus: TaggingStatus.done,
      candidates: [
        _cand('cup', .2),
        _cand('table', .4),
        _cand('spoon', .6),
        _cand('drink', .8, pos: 'verb'),
      ]));
  return (repo: repo, pack: _pack());
}

void main() {
  test('改字：重查詞庫、原標籤保留、AI 的字不再推薦', () {
    final (:repo, :pack) = _setup();
    final s = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    final cup = s.words.firstWhere((w) => w.word == 'cup');
    // The dialog is prefilled with the old meaning: left as is, the pack's
    // sense is used; a form leads to its lemma.
    s.correct(cup, word: 'Mugs', meaning: cup.candidate.meaning);
    final mug = s.words.firstWhere((w) => w.word == 'mug');
    expect(mug.candidate.meaning, '馬克杯');
    expect(mug.candidate.level, 'B1');
    expect(mug.candidate.lexemeId, 7);
    expect(s.words.any((w) => w.word == 'cup'), isFalse);
    s.save();

    final occ = repo.activeLabels('p').firstWhere((l) => l.entry.word == 'mug');
    expect(occ.occ.aiLabel, 'cup', reason: '原標籤保留');
    expect(occ.occ.userEdited, isTrue, reason: '標成使用者修正');
    expect(repo.photo('p')!.rejectedWords, contains('cup'));

    // Reopened, and the dial moved all the way: cup never comes back, mug
    // (the learner's word) stays.
    final again = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    for (final t in [0, 5, 2]) {
      again.setTarget(t);
      expect(again.words.map((w) => w.word), isNot(contains('cup')));
      expect(again.words.map((w) => w.word), contains('mug'));
    }
  });

  test('改字時自己打的中文優先，且背景更新不覆蓋', () {
    final (:repo, :pack) = _setup();
    final s = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    final cup = s.words.firstWhere((w) => w.word == 'cup');
    s.correct(cup, word: 'mug', meaning: '咖啡杯');
    s.save();
    final e = repo.entryByWord('mug')!;
    expect(e.meaning, '咖啡杯');
    expect(e.userEdited, contains(WordField.meaning));
  });

  test('刪掉錯的：不算已學會，重新開也不會再出現', () {
    final (:repo, :pack) = _setup();
    final s = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    s.save();
    final spoon = s.words.firstWhere((w) => w.word == 'spoon');
    s.delete(spoon);
    expect(s.words.map((w) => w.word), isNot(contains('spoon')));
    s.save();
    expect(repo.profile.learned, isNot(contains('spoon')), reason: '不是已學會');
    expect(repo.entryByWord('spoon'), isNull, reason: '沒複習過的卡一起移除');
    expect(repo.photo('p'), isNotNull);
    final again = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    again.setTarget(0);
    again.setTarget(5);
    expect(again.words.map((w) => w.word), isNot(contains('spoon')));
    expect(again.oldWords.map((w) => w.word), isNot(contains('spoon')));
  });

  test('自己加字：放了位置有標籤，沒放就不標；進收藏與複習；缺詞送請求', () {
    final (:repo, :pack) = _setup();
    final s = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    final placed = s.add(word: 'mug', at: const LabelPoint(.3, .7))!;
    expect(placed.placed, isTrue);
    expect(placed.candidate.meaning, '馬克杯');
    final loose = s.add(word: 'Saucer', meaning: '小碟子')!;
    expect(loose.placed, isFalse);
    expect(loose.candidate.lexemeId, isNull);
    expect(pack.requests.keys, contains('missing_lexeme:saucer:noun'),
        reason: '詞庫沒有的字送缺詞請求');
    // The dial never drops the learner's words.
    s.setTarget(5);
    expect(s.words.map((w) => w.word), containsAll(['mug', 'saucer']));
    s.save();

    for (final w in ['mug', 'saucer']) {
      final e = repo.entryByWord(w)!;
      expect(repo.cardOf(e.id), isNotNull, reason: '$w 照常建立卡片');
    }
    final labels = {for (final l in repo.activeLabels('p')) l.entry.word: l.occ};
    expect(labels['mug']!.placed, isTrue);
    expect(labels['mug']!.anchor.x, .3);
    expect(labels['mug']!.aiLabel, isNull, reason: '使用者自己加的字沒有 AI 標籤');
    expect(labels['saucer']!.placed, isFalse);

    // Reopened: still the learner's; placing it later gives it a pin.
    final again = PhotoWordSession(repo: repo, photoId: 'p', pack: pack);
    final saucer = again.words.firstWhere((w) => w.word == 'saucer');
    expect(saucer.added, isTrue);
    expect(saucer.placed, isFalse);
    again.move(saucer, const LabelPoint(.5, .2));
    again.save();
    final occ = repo.activeLabels('p').firstWhere((l) => l.entry.word == 'saucer');
    expect(occ.occ.placed, isTrue);
    expect(occ.occ.anchor.y, .2);
  });

  test('沒有位置的標籤存檔再讀回來還是沒有位置', () {
    const o = PhotoOccurrence(
        id: 'o',
        photoId: 'p',
        wordEntryId: 'e',
        anchor: LabelPoint(.5, .5),
        placed: false);
    expect(PhotoOccurrence.fromJson(o.toJson()).placed, isFalse);
    expect(PhotoOccurrence.fromJson(o.copyWith(anchor: const LabelPoint(.1, .1)).toJson()).placed,
        isTrue);
    final p = Photo(
        id: 'p',
        title: 'p',
        takenAt: testNow,
        createdAt: testNow,
        rejectedWords: const ['cup']);
    expect(Photo.fromJson(p.toJson()).rejectedWords, ['cup']);
    expect(Photo.fromJson(p.copyWith(title: 'x').toJson()).rejectedWords, ['cup']);
  });

  group('照片詳情畫面', () {
    tearDown(() => LexiconPack.instance.clear());

    testWidgets('自己加字 → 點照片放位置；點標籤可刪除', (tester) async {
      final app = await pumpApp(tester, initialTab: AppTab.album);
      app.navigator.openPhoto('photo-breakfast');
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('add-word')));
      await tester.pumpAndSettle();
      expect(find.text('自己加字'), findsWidgets);
      await tester.enterText(find.byType(TextField).first, 'teapot');
      await tester.tap(find.text('儲存'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('placing-bar')), findsOneWidget);
      expect(find.byKey(const ValueKey('word:teapot')), findsOneWidget,
          reason: '新加的字進列表');
      final pinsBefore = tester
          .widget<PinnedPhoto>(find.byType(PinnedPhoto))
          .pins
          .map((p) => p.id);
      expect(pinsBefore, isNot(contains('teapot')), reason: '還沒放就沒有標籤');

      // Tap an empty spot of the photo (its lower-left part).
      final photo = tester.getRect(find.byType(PinnedPhoto));
      await tester.tapAt(photo.bottomLeft + const Offset(90, -30));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('placing-bar')), findsNothing);
      final pin = tester
          .widget<PinnedPhoto>(find.byType(PinnedPhoto))
          .pins
          .firstWhere((p) => p.id == 'teapot');
      expect(pin.anchor.y, greaterThan(.5));
      expect(LexiconPack.instance.requests.keys,
          isNot(contains('missing_lexeme:teapot:noun')),
          reason: '沒有語言包時不送缺詞（詞庫尚未下載）');

      // Delete apple as wrong: gone, and not in 已學會.
      final row = find.byKey(const ValueKey('word:apple'));
      await tester.ensureVisible(row);
      await tester.tap(
          find.descendant(of: row, matching: find.byIcon(Icons.more_horiz)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('刪除（照片裡沒有這個）'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('word:apple')), findsNothing);
      expect(app.repository.profile.learned, isNot(contains('apple')));
      expect(tester.takeException(), isNull);
    });

    testWidgets('加字選「不放位置」：列表有字、照片上沒有標籤', (tester) async {
      final app = await pumpApp(tester, initialTab: AppTab.album);
      app.navigator.openPhoto('photo-breakfast');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('add-word')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'napkin');
      await tester.enterText(find.byType(TextField).last, '餐巾');
      await tester.tap(find.text('儲存'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('不放位置'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('placing-bar')), findsNothing);
      expect(find.byKey(const ValueKey('word:napkin')), findsOneWidget);
      expect(
          tester
              .widget<PinnedPhoto>(find.byType(PinnedPhoto))
              .pins
              .map((p) => p.id),
          isNot(contains('napkin')));
      expect(tester.takeException(), isNull);
    });
  });
}
