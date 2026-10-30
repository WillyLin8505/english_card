import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

/// 複習 landing tiles show a cover (owner, 2026-10-23): an album's newest
/// photo; 綜合／今天新加的／弱項 a photo of one of their words.
void main() {
  testWidgets('every 複習 tile with photos shows a cover', (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.review, size: const Size(402, 1600));
    await tester.pumpAndSettle();
    expect(find.text('想複習哪一本？'), findsOneWidget);
    final repo = app.repository;

    // 綜合 uses a photo of a word being learned.
    final all = repo.reviewCoverPhoto(null);
    expect(all, isNotNull);
    final allTile = find.ancestor(
        of: find.text('綜合'), matching: find.bySemanticsLabel(RegExp('^綜合, ')));
    expect(allTile, findsOneWidget);
    expect(
        find.descendant(of: allTile, matching: find.byType(PhotoImage)),
        findsOneWidget);

    // Each album tile: its newest photo (or its bundled cover).
    for (final a in repo.albums) {
      final tile = find.bySemanticsLabel(RegExp('^${RegExp.escape(a.name)}, '));
      if (tile.evaluate().isEmpty) continue;
      final pictures = find.descendant(
          of: tile,
          matching: find.byWidgetPredicate((w) => w is PhotoImage || w is Image));
      if (a.coverAsset != null || repo.albumCoverPhoto(a.id) != null) {
        expect(pictures, findsWidgets, reason: a.name);
      }
    }

    // A word set without photos falls back to a plain block.
    expect(repo.reviewCoverPhoto(<String>{}), isNull);
  });
}
