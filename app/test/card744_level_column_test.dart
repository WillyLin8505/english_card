import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/photo_word_grid.dart';
import 'package:photo_english_app/widgets/mobile/level_column_panel.dart';

GridWord w(String word, String pos, String level) => GridWord(
    word: word, pos: pos, level: level, meaning: '', tagId: null, point: null);

void main() {
  final grid = buildPhotoWordGrid([
    w('dog', 'noun', 'A1'),
    w('run', 'verb', 'A1'),
    w('big', 'adjective', 'A1'),
    w('canine', 'noun', 'C1'),
    w('look up', 'phrase', 'A1'),
  ]);

  Widget host(int level) => MaterialApp(
      home: Scaffold(
          body: LevelColumnPanel(grid: grid, level: level, onWordTap: (_) {})));

  testWidgets('A1: four parts of speech, empty adverb hint, no phrase',
      (t) async {
    await t.pumpWidget(host(0));
    for (final r in ['noun', 'verb', 'adjective', 'adverb']) {
      expect(find.byKey(ValueKey('level-row-$r')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('level-row-phrase')), findsNothing);
    expect(find.byKey(const ValueKey('level-word:look up')), findsNothing);
    expect(find.byKey(const ValueKey('level-word:dog')), findsOneWidget);
    expect(find.text('這個難度沒有合適的副詞'), findsOneWidget);
    expect(find.byKey(const ValueKey('pos-filter-all')), findsNothing);
  });

  testWidgets('changing level swaps the column but keeps all four rows',
      (t) async {
    await t.pumpWidget(host(4));
    expect(find.byKey(const ValueKey('level-word:canine')), findsOneWidget);
    expect(find.byKey(const ValueKey('level-word:dog')), findsNothing);
    for (final r in ['noun', 'verb', 'adjective', 'adverb']) {
      expect(find.byKey(ValueKey('level-row-$r')), findsOneWidget);
    }
    expect(find.text('這個難度沒有合適的動詞'), findsOneWidget);
  });
}
