import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/photo_detail_screen.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

// 問題回報：Mac 實機量測照片詳情開啟 114ms（M-PERF）: the whole page was built
// in the first frame. Now the photo comes first, the labels and the word
// list follow one frame at a time.
// 問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）: the bar,
// the words a phone shows, the other words and what is under the list come
// one frame each, without rebuilding what is already there.
void main() {
  testWidgets('照片詳情第一個畫面就有照片，標籤與單字列表隨後出現', (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    app.navigator.openPhoto('photo-breakfast');
    final screen = find.byType(PhotoDetailScreen);
    for (var i = 0; i < 3 && screen.evaluate().isEmpty; i++) {
      await tester.pump();
    }
    Finder inScreen(Finder f) => find.descendant(of: screen, matching: f);

    // Frame 0: the title and the photo only.
    expect(inScreen(find.text('照片詳情')), findsOneWidget);
    expect(inScreen(find.byType(PhotoImage)), findsOneWidget);
    expect(inScreen(find.byType(PinnedPhoto)), findsNothing);
    expect(inScreen(find.byType(Dismissible)), findsNothing);

    // Frame 1: the labels, shown at once (not popping in as new ones).
    await tester.pump();
    expect(inScreen(find.byType(PinnedPhoto)), findsOneWidget);
    expect(inScreen(find.text('Coffee')), findsOneWidget, reason: 'the pin');
    expect(find.text('跳過動畫'), findsNothing);
    expect(inScreen(find.byType(Dismissible)), findsNothing);

    // Frame 2: the difficulty bar and the list title; then two words a
    // frame.
    await tester.pump();
    expect(find.byKey(const ValueKey('difficulty-bar')), findsOneWidget);
    expect(find.text('辨識單字列表 (5)'), findsOneWidget);
    expect(inScreen(find.byType(Dismissible)), findsNothing);
    for (final n in [2, 4, 5]) {
      await tester.pump();
      expect(inScreen(find.byType(Dismissible)), findsNWidgets(n));
      expect(find.byKey(const ValueKey('add-word')), findsNothing);
    }

    // Then the shortcuts, then the notes under the list.
    await tester.pump();
    expect(find.byKey(const ValueKey('add-word')), findsOneWidget);
    expect(find.text('返回時自動保存，不用再按建立。'), findsNothing);
    await tester.pump();
    expect(find.text('返回時自動保存，不用再按建立。'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(inScreen(find.text('Coffee')), findsNWidgets(2)); // pin + card
    expect(find.text('跳過動畫'), findsNothing);
  });
}
