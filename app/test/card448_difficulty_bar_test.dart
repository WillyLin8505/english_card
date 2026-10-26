import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/photo_detail_screen.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

// 問題回報 #442: a photo with three labels per level. Words within a level
// share no stem or meaning, so the selector may pick any of them.
const _byLevel = {
  'A1': ['cat', 'run', 'red'],
  'A2': ['bread', 'jump', 'quiet'],
  'B1': ['window', 'paint', 'gentle'],
  'B2': ['harbor', 'decide', 'fragile'],
  'C1': ['summit', 'navigate', 'obscure'],
  'C2': ['quarrel', 'eloquent', 'meticulous'],
};

const _pos = {
  'cat': 'noun',
  'run': 'verb',
  'red': 'adj.',
  'bread': 'noun',
  'jump': 'verb',
  'quiet': 'adj.',
  'window': 'noun',
  'paint': 'verb',
  'gentle': 'adj.',
  'harbor': 'noun',
  'decide': 'verb',
  'fragile': 'adj.',
  'summit': 'noun',
  'navigate': 'verb',
  'obscure': 'adj.',
  'quarrel': 'noun',
  'eloquent': 'adj.',
  'meticulous': 'adj.',
};

List<WordCandidate> _pool() => [
      for (final MapEntry(key: level, value: words) in _byLevel.entries)
        for (final (i, w) in words.indexed)
          WordCandidate(
            word: w,
            pos: _pos[w]!,
            meaning: '$w 義',
            level: level,
            levelSource: 'cefr-j',
            evidence: 'seen',
            point: LabelPoint(0.1 + i * 0.25, 0.1 + levelIndex(level) * 0.12),
            visualConfidence: 0.9,
            usefulness: 0.8,
          ),
    ];

void main() {
  final profile = UserVocabularyProfile.start('B1', now: testNow);

  test('every difficulty position shows five labels', () {
    for (var target = 0; target < cefrLevels.length; target++) {
      final sel = const WordSelector().select(
        pool: _pool(),
        target: target,
        profile: profile,
        now: testNow,
      );
      expect(sel.words.length, WordSelector.maxWords,
          reason: 'target ${cefrLevels[target]}');
    }
  });

  test('dragging harder drops the easy labels and brings in harder ones', () {
    List<String> levelsAt(int target) => [
          for (final c in const WordSelector()
              .select(
                pool: _pool(),
                target: target,
                profile: profile,
                now: testNow,
              )
              .words)
            c.level
        ];

    final atA1 = levelsAt(0);
    final atC2 = levelsAt(5);
    expect(atA1, contains('A1'));
    expect(atC2, isNot(contains('A1')));
    expect(atC2, isNot(contains('A2')));
    expect(atC2, contains('C2'));
  });

  test('a short pool shows every label it has', () {
    final few = _pool().take(3).toList();
    final sel = const WordSelector().select(
      pool: few,
      target: 2,
      profile: profile,
      now: testNow,
    );
    expect(sel.words.length, 3);
    expect(sel.topUp, isNotNull, reason: 'the model is asked for more');
  });

  testWidgets('the difficulty bar shows and settles on taps and drags',
      (tester) async {
    final moved = <int>[];
    final settled = <int>[];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 360,
          child: PhotoDifficultyBar(
            target: 0,
            offset: 0,
            onMove: moved.add,
            onSelect: settled.add,
          ),
        ),
      ),
    ));

    expect(find.bySemanticsLabel(RegExp('單字難度')), findsOneWidget);
    expect(find.textContaining('剛好'), findsOneWidget);
    // 問題回報 #708: a thick bar without the A1…C2 ticks; the level's name
    // and 簡單／難 at the ends tell where the thumb is.
    expect(find.text('入門 · 剛好'), findsOneWidget);
    for (final l in cefrLevels) {
      expect(find.text(l), findsNothing);
    }
    expect(find.text('簡單'), findsOneWidget);
    expect(find.text('難'), findsOneWidget);
    expect(tester.getSize(find.byKey(const ValueKey('difficulty-track'))).height,
        greaterThanOrEqualTo(12));
    expect(tester.getSize(find.byKey(const ValueKey('difficulty-thumb'))).width,
        greaterThanOrEqualTo(32));

    // Tap the C2 end of the bar.
    final bar = tester.getRect(find.byType(PhotoDifficultyBar));
    await tester.tapAt(Offset(bar.right - 20, bar.center.dy));
    await tester.pump();
    expect(settled, [5]);

    // Drag from the left end to the right end: each step moves, and the
    // drag ends on the level it reached.
    await tester.dragFrom(
        Offset(bar.left + 20, bar.center.dy), Offset(bar.width - 40, 0));
    await tester.pump();
    expect(moved, isNotEmpty);
    expect(moved.last, 5);
    expect(settled, [5, 0]);
  });
}
