import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 問題回報 #444: the photo page showed the learner's level twice — the bar
// under the photo already says「入門（A1）· 剛好」, and the row above the list
// repeated it as「單字難度 入門（A1）· 剛好」.
void main() {
  testWidgets('the level is shown once on the photo page', (tester) async {
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        profile: UserVocabularyProfile.start('A1', now: testNow));
    const words = ['cat', 'run', 'red'];
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'p1',
        takenAt: testNow,
        createdAt: testNow,
        placeholderColors: const [0xFF8899AA, 0xFF334455],
        width: 1200,
        height: 900,
        taggingStatus: TaggingStatus.done,
        candidates: [
          for (final (i, w) in words.indexed)
            WordCandidate(
              word: w,
              pos: 'noun',
              meaning: '$w 義',
              level: 'A1',
              levelSource: 'cefr-j',
              evidence: 'seen',
              point: LabelPoint(0.1 + i * 0.25, 0.2),
              visualConfidence: 0.9,
              usefulness: 0.8,
            ),
        ]));

    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        repository: repo,
        size: const Size(390, 844));
    app.navigator.openPhoto('p1');
    await tester.pumpAndSettle();

    expect(find.textContaining('單字難度'), findsNothing);
    expect(find.textContaining('多看動詞'), findsOneWidget);
    expect(find.textContaining('剛好'), findsOneWidget);
  });

  // 問題回報 #451: the shortcut pills sit under the word list, so the first
  // word is the first row under the list title.
  testWidgets('the first word comes before the level shortcuts', (tester) async {
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        profile: UserVocabularyProfile.start('A1', now: testNow));
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'p1',
        takenAt: testNow,
        createdAt: testNow,
        placeholderColors: const [0xFF8899AA, 0xFF334455],
        width: 1200,
        height: 900,
        taggingStatus: TaggingStatus.done,
        candidates: [
          const WordCandidate(
            word: 'cat',
            pos: 'noun',
            meaning: 'cat 義',
            level: 'A1',
            levelSource: 'cefr-j',
            evidence: 'seen',
            point: LabelPoint(0.1, 0.2),
            visualConfidence: 0.9,
            usefulness: 0.8,
          ),
        ]));

    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        repository: repo,
        size: const Size(390, 844));
    app.navigator.openPhoto('p1');
    await tester.pumpAndSettle();

    final word = tester.getTopLeft(find.byKey(const ValueKey('word:cat')));
    final pills = tester.getTopLeft(find.textContaining('多看動詞'));
    expect(word.dy, lessThan(pills.dy));
  });

  // 問題回報 #451 (owner 10/21): the auto-save note moves below the list too,
  // so under the photo only the difficulty bar is left.
  testWidgets('the auto-save note sits below the first word', (tester) async {
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        profile: UserVocabularyProfile.start('A1', now: testNow));
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'p1',
        takenAt: testNow,
        createdAt: testNow,
        placeholderColors: const [0xFF8899AA, 0xFF334455],
        width: 1200,
        height: 900,
        taggingStatus: TaggingStatus.done,
        candidates: [
          const WordCandidate(
            word: 'cat',
            pos: 'noun',
            meaning: 'cat 義',
            level: 'A1',
            levelSource: 'cefr-j',
            evidence: 'seen',
            point: LabelPoint(0.1, 0.2),
            visualConfidence: 0.9,
            usefulness: 0.8,
          ),
        ]));

    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        repository: repo,
        size: const Size(390, 844));
    app.navigator.openPhoto('p1');
    await tester.pumpAndSettle();

    final bar = tester.getTopLeft(find.byKey(const ValueKey('difficulty-bar')));
    final word = tester.getTopLeft(find.byKey(const ValueKey('word:cat')));
    final note = tester.getTopLeft(find.textContaining('返回時自動保存'));
    expect(bar.dy, lessThan(word.dy));
    expect(word.dy, lessThan(note.dy));
  });
}
