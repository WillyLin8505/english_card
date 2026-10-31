import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'helpers.dart';

LexiconPack usagePack() => LexiconPack()
  ..loadJson({
    'target_language': 'en',
    'native_language': 'zh-TW',
    'lexemes': [
      for (final row in [
        (1, 'noun', 'contest', 'It was a good match.'),
        (2, 'verb', 'compatible', 'These colors match well.')
      ])
        {
          'id': row.$1,
          'lemma': 'match',
          'normalized': 'match',
          'pos': row.$2,
          'status': 'full',
          'cefr': 'A1',
          'senses': [
            {'id': row.$1 * 10, 'definition': row.$3, 'native': row.$3}
          ],
          'examples': [
            {
              'text': row.$4,
              'translation': row.$3,
              'sense_id': row.$1 * 10,
              'level': 'A1'
            }
          ]
        },
    ],
  });

void main() {
  testWidgets('word list retains usages while card back focuses on primary meaning',
      (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addWord(word: 'match', pos: 'noun', meaning: 'custom');
    repo.linkLexicon(usagePack());
    final app =
        await pumpApp(tester, repository: repo, initialTab: AppTab.words);
    expect(find.text('名詞・動詞'), findsOneWidget);
    app.navigator.selectTab(AppTab.review);
    await tester.pumpAndSettle();
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'match');
    await tester.tap(find.byTooltip('送出答案'));
    await tester.pumpAndSettle();
    // 問題回報 #1167: the review back omits the 詞性與意思 title.
    expect(find.text('詞性與意思'), findsNothing);
    expect(find.text('各詞性釋義'), findsNothing);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('動詞'), findsNothing);
    expect(repo.entryByWord('match')!.effectiveUsages, hasLength(2));
  });

  testWidgets(
      'card back follows the usage actually tested, not the entry\'s default usage',
      (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addWord(word: 'match', pos: 'noun', meaning: 'custom');
    repo.linkLexicon(usagePack());
    await pumpApp(tester, repository: repo, initialTab: AppTab.review);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'match');
    await tester.tap(find.byTooltip('送出答案'));
    await tester.pumpAndSettle();
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('動詞'), findsNothing);
    await tester.tap(find.text('忘記'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'match');
    await tester.tap(find.byTooltip('送出答案'));
    await tester.pumpAndSettle();
    expect(find.text('動詞'), findsOneWidget);
    expect(find.text('名詞'), findsNothing);
  });

  test('one spelling/card retains both usages through sync and persistence',
      () {
    final repo = WordDatabaseRepository();
    final e = repo.addWord(word: ' Match ', pos: 'noun', meaning: 'custom');
    final pack = usagePack();
    repo.linkLexicon(pack);
    final linked = repo.entry(e.id)!;
    expect(repo.entries.length, 1);
    expect(linked.partsOfSpeech, ['noun', 'verb']);
    expect(repo.partsOfSpeech, contains('verb'));
    expect(repo.query(const WordDatabaseFilter(pos: 'verb')).single.entry.id,
        e.id);
    final saved = WordEntry.fromJson(linked.toJson());
    expect(saved.usages.length, 2);
    expect(saved.usages[1].examples.single.senseId, 'pack:en:20');
    expect(repo.linkLexicon(pack), 0);
    expect(() => repo.addWord(word: 'match', pos: 'verb', meaning: 'custom'),
        throwsA(isA<DuplicateWordException>()));
    expect(repo.cardOf(e.id), isNotNull);
    repo.dispose();
  });

  test('new words use the already linked pack', () {
    final repo = WordDatabaseRepository()..linkLexicon(usagePack());
    final e = repo.addWord(word: 'match', pos: 'noun', meaning: 'custom');
    expect(e.usages.length, 2);
    repo.dispose();
  });

  test('each exercise freezes actual usage and bound sense across a sync', () {
    final repo = WordDatabaseRepository();
    final e = repo.addWord(word: 'match', pos: 'noun', meaning: 'custom');
    final pack = usagePack();
    repo.linkLexicon(pack);
    final session = FlashcardSession(repo, lexicon: pack);
    expect(session.exercise!.prompt, contains('good'));
    session.submitAnswer('match');
    repo.linkLexicon(pack);
    session.rate(Rating.again);
    final noun = repo.logsOf(repo.cardOf(e.id)!.id).single;
    expect(noun.usageId, 'pack:en:1');
    expect(noun.senseId, 'pack:en:10');
    expect(session.exercise!.prompt, contains('colors'));
    session.submitAnswer('match');
    session.rate(Rating.good);
    final verb = repo.logsOf(repo.cardOf(e.id)!.id).last;
    expect(verb.usageId, 'pack:en:2');
    expect(verb.senseId, 'pack:en:20');
    expect(ReviewLog.fromJson(verb.toJson()).senseId, verb.senseId);
    final old = verb.toJson()
      ..remove('usage_id')
      ..remove('sense_id');
    expect(ReviewLog.fromJson(old).usageId, isNull);
    session.dispose();
    repo.dispose();
  });

  test('legacy words get stable local ids and later edits stay authoritative',
      () {
    final now = DateTime(2026);
    final old = WordEntry(
        id: 'old',
        word: 'match',
        pos: 'noun',
        meaning: 'custom',
        createdAt: now,
        updatedAt: now);
    final json = old.toJson()..remove('lexeme_usages');
    final restored = WordEntry.fromJson(json);
    final saved =
        WordEntry.fromJson(restored.toJson()).copyWith(meaning: 'edited');
    expect(saved.effectiveUsages.single.id, 'local:old');
    expect(saved.effectiveUsages.single.senses.single.meaning, 'edited');
    final linked = old.copyWith(
        usages: usagePack().usagesFor('match'),
        meaning: 'custom',
        userEdited: {WordField.meaning});
    expect(linked.effectiveUsages.first.senses.single.meaning, 'custom');
    expect(linked.effectiveUsages.last.senses.single.meaning, 'compatible');
  });

  test('unbound multi-sense examples never acquire an invented sense', () {
    final now = DateTime(2026);
    final entry = WordEntry(
        id: 'x',
        word: 'match',
        pos: 'noun',
        meaning: 'contest',
        createdAt: now,
        updatedAt: now,
        usages: const [
          LexemeUsage(id: 'u', pos: 'noun', senses: [
            WordSense(id: 's1', meaning: 'contest'),
            WordSense(id: 's2', meaning: 'fire stick'),
          ], examples: [
            WordExample(text: 'It is a match.', translation: 'ambiguous')
          ]),
        ]);
    final repo = WordDatabaseRepository(entries: [
      entry
    ], cards: [
      const LearningCard(id: 'c', wordEntryId: 'x', templateId: 't'),
    ]);
    final session = FlashcardSession(repo);
    // No safe exercise falls back to the traditional flip card rather than
    // skipping the card (問題回報 #207 decision A).
    expect(session.finished, isFalse);
    expect(session.exercise, isNull);
    expect(repo.logsOf('c'), isEmpty);
    session.dispose();
    repo.dispose();
  });
}
