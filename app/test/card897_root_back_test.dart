import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/album_screen.dart';
import 'package:photo_english_app/screens/word_database_screen.dart';

import 'helpers.dart';

// 卡 #897 (owner, 2026-10-31): the 相片冊, 單字本 and 複習 tab roots have no
// screen above them, so they show no 返回; a page pushed from another one
// keeps it and goes back.
const _back = '返回';

/// A host page with one button that pushes [child] like the tabs do.
Widget _host(Widget Function() child) => Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => child())),
          child: const Text('go'),
        ),
      ),
    );

void main() {
  testWidgets('the 相片冊 tab root has no 返回', (tester) async {
    await pumpApp(tester, initialTab: AppTab.album);
    expect(find.bySemanticsLabel(_back), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the 單字本 tab root has no 返回', (tester) async {
    await pumpApp(tester, initialTab: AppTab.words);
    expect(find.bySemanticsLabel(_back), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the 複習 tab start page has no 返回', (tester) async {
    await pumpApp(tester, initialTab: AppTab.review);
    expect(find.bySemanticsLabel(_back), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a pushed 相片冊 keeps 返回 and it pops', (tester) async {
    await pumpApp(tester,
        home: _host(() => const AlbumScreen()));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(_back), findsOneWidget);
    await tester.tap(find.bySemanticsLabel(_back));
    await tester.pumpAndSettle();
    expect(find.text('go'), findsOneWidget);
  });

  testWidgets('a pushed 單字本 keeps 返回 and it pops', (tester) async {
    await pumpApp(tester,
        home: _host(() => const WordDatabaseScreen()));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(_back), findsOneWidget);
    await tester.tap(find.bySemanticsLabel(_back));
    await tester.pumpAndSettle();
    expect(find.text('go'), findsOneWidget);
  });

  testWidgets('the 單字本 embedded in the library keeps 返回 to its toggle',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.tap(find.text('我的單字本'));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.bySemanticsLabel(_back), findsOneWidget);
    await tester.tap(find.bySemanticsLabel(_back));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.bySemanticsLabel(_back), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
