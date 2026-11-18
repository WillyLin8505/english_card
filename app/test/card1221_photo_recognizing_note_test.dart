// 問題回報 #1668（owner，照片詳情）:「還在辨識中的時候要顯示還在辨識中，不然我不知道你還有沒有在辨識單字」.
// A photo that already has labels still gets recognition from the queue; the
// note under the difficulty bar must say 「AI 辨識中…」 while it runs (the
// label sweep stays off the photo, #939), and it goes away once done.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/app/app_scope.dart';

import 'helpers.dart';

void main() {
  testWidgets('#1668 a photo with labels says 辨識中 while it is recognized',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    final repo = app.repository;
    final before = repo.photo('photo-breakfast')!;
    expect(before.candidates, isNotEmpty);

    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    expect(find.text('AI 辨識中…'), findsNothing);

    repo.updatePhoto(before.copyWith(taggingStatus: TaggingStatus.tagging));
    await tester.pump();
    expect(find.text('AI 辨識中…'), findsOneWidget);
    // #939: the labels stay usable, nothing covers them.
    expect(find.text('AI 正在找單字…'), findsNothing);

    repo.updatePhoto(before.copyWith(taggingStatus: TaggingStatus.done));
    await tester.pump();
    expect(find.text('AI 辨識中…'), findsNothing);
  });
}
