// M180 (owner #732): 照片詳情 gets a 「詞性 × CEFR」 table under the
// photo — rows 動詞／名詞／形容詞／副詞／片語, columns A1–C2; a word in
// the word book opens 單字詳情, another can be added; scrolls sideways on
// a narrow phone; empty cells show a dash.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/photo_word_grid.dart';
import 'package:photo_english_app/widgets/mobile/photo_word_grid_table.dart';

import 'helpers.dart';

GridWord _w(String word, String pos, String level, {String? tag}) =>
    GridWord(word: word, pos: pos, level: level, tagId: tag);

void main() {
  group('buildPhotoWordGrid', () {
    test('groups by part of speech and level', () {
      final g = buildPhotoWordGrid([
        _w('happy', 'adj', 'A1', tag: 't1'),
        _w('joyful', 'adjective', 'B2', tag: 't1'),
        _w('elated', 'adj.', 'C1', tag: 't1'),
        _w('run', 'verb', 'A1'),
        _w('cup', 'noun', 'A1'),
        _w('quickly', 'adv.', 'A2'),
        _w('pick up', 'phrasal verb', 'A2'),
        _w('piece of cake', 'idiom', 'B2'),
        _w('on the table', 'phrase', 'A1'),
      ]);
      List<String> at(GridRow r, String l) => [
            for (final w
                in g.cell(r, ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'].indexOf(l)))
              w.word
          ];
      expect(at(GridRow.adjective, 'A1'), ['happy']);
      expect(at(GridRow.adjective, 'B2'), ['joyful']);
      expect(at(GridRow.adjective, 'C1'), ['elated']);
      expect(g.cell(GridRow.adjective, 4).single.tagId, 't1');
      expect(at(GridRow.verb, 'A1'), ['run']);
      expect(at(GridRow.noun, 'A1'), ['cup']);
      expect(at(GridRow.adverb, 'A2'), ['quickly']);
      expect(at(GridRow.phrase, 'A2'), ['pick up']);
      expect(at(GridRow.phrase, 'B2'), ['piece of cake']);
      expect(at(GridRow.phrase, 'A1'), ['on the table']);
      expect(g.cell(GridRow.verb, 5), isEmpty);
      expect(g.isEmpty, isFalse);
    });

    test('other parts of speech: multi-word → 片語, single word skipped', () {
      final g = buildPhotoWordGrid([
        _w('the', 'determiner', 'A1'),
        _w('in front of', 'preposition', 'A2'),
        _w('cup', 'noun', 'A1'),
        _w('cup', 'verb', 'B1'), // same word twice: first one wins
        _w('thing', 'noun', 'Z9'), // no level: left out
      ]);
      expect(g.cell(GridRow.phrase, 1).single.word, 'in front of');
      final all = [
        for (final r in GridRow.values)
          for (var i = 0; i < 6; i++) ...g.cell(r, i).map((w) => w.word)
      ];
      expect(all..sort(), ['cup', 'in front of']);
    });

    test('nothing to show', () {
      expect(buildPhotoWordGrid(const []).isEmpty, isTrue);
    });
  });

  testWidgets('the table renders, scrolls sideways at 375pt, taps a word',
      (tester) async {
    final grid = buildPhotoWordGrid([
      const GridWord(
          word: 'happy', pos: 'adj', level: 'A1', point: LabelPoint(0.5, 0.5)),
      _w('elated', 'adj', 'C2'),
    ]);
    GridWord? tapped;
    tester.view.physicalSize = const Size(375, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(20),
          child: PhotoWordGridTable(
            grid: grid,
            known: const {'happy'},
            onWordTap: (w) => tapped = w,
          ),
        ),
      ),
    ));
    expect(tester.takeException(), isNull);
    for (final h in ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']) {
      expect(find.text(h), findsOneWidget);
    }
    for (final r in ['動詞', '名詞', '形容詞', '副詞', '片語']) {
      expect(find.text(r), findsOneWidget);
    }
    // 5 rows × 6 levels minus the two words.
    expect(find.text('–'), findsNWidgets(28));
    await tester.tap(find.byKey(const ValueKey('grid-word:happy')));
    expect(tapped?.word, 'happy');

    // C2 is off screen on a 375pt phone; the table scrolls to it.
    final elated = find.byKey(const ValueKey('grid-word:elated'));
    expect(tester.getRect(elated).left, greaterThan(375));
    await tester.drag(find.byKey(const ValueKey('photo-word-grid-scroll')),
        const Offset(-400, 0));
    await tester.pumpAndSettle();
    expect(tester.getRect(elated).right, lessThan(375));
    await tester.tap(elated);
    expect(tapped?.word, 'elated');
  });

  testWidgets('M189: with the flag off (the default) 照片詳情 has no table',
      (tester) async {
    expect(photoWordGridFlag, isFalse);
    expect(showPhotoWordGrid, isFalse);
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(375, 812));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const ValueKey('add-word')), 300,
        scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    expect(find.byType(PhotoWordGridTable), findsNothing);
    expect(find.byKey(const ValueKey('photo-word-grid')), findsNothing);
  });

  testWidgets('照片詳情: grid under the list; open a listed word, add another',
      (tester) async {
    showPhotoWordGrid = true;
    addTearDown(() => showPhotoWordGrid = photoWordGridFlag);
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(375, 812));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    final grid = find.byKey(const ValueKey('photo-word-grid'));
    await tester.scrollUntilVisible(grid, 300,
        scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    expect(grid, findsOneWidget);
    // Below the 辨識單字列表 and its add-word button.
    expect(
        tester.getTopLeft(grid).dy,
        greaterThan(
            tester.getTopLeft(find.byKey(const ValueKey('add-word'))).dy));

    // A word not on the photo's list: rustic (adjective, B1).
    final listed = find.byKey(const ValueKey('word:rustic'));
    final chip = find.byKey(const ValueKey('grid-word:rustic'));
    expect(chip, findsOneWidget);
    expect(listed, findsNothing);
    expect(app.repository.entryByWord('rustic'), isNull);
    await tester.ensureVisible(chip);
    await tester.pumpAndSettle();
    await tester.tap(chip);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('grid-add')));
    await tester.pumpAndSettle();
    expect(find.text('已加入「Rustic」'), findsOneWidget);
    expect(find.byKey(const ValueKey('word:rustic')), findsOneWidget);

    // A listed word opens 單字詳情 (saved first).
    final first = find.byKey(const ValueKey('grid-word:rustic'));
    await tester.ensureVisible(first);
    await tester.pumpAndSettle();
    await tester.tap(first);
    await tester.pumpAndSettle();
    expect(find.byType(WordDetailScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
