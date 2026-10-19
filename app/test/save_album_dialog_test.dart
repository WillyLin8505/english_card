import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

void main() {
  test('camera and picker share one default photo name with date and time',
      () {
    // 問題回報 #313: was 「拍攝於 14:32」 vs 「新照片 10/19」.
    expect(defaultPhotoTitle(DateTime(2026, 10, 19, 14, 32)), '10/19 14:32');
    expect(defaultPhotoTitle(DateTime(2026, 3, 5, 8, 5)), '3/5 08:05');
  });

  testWidgets('a photo cannot be saved until an album is selected or named',
      (tester) async {
    final repository = WordDatabaseRepository();
    SavePhotoChoice? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) {
        return FilledButton(
          onPressed: () async {
            result = await showSaveToAlbumDialog(
              context,
              repository: repository,
              defaultTitle: '照片',
            );
          },
          child: const Text('開啟'),
        );
      }),
    ));

    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    FilledButton save() => tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '儲存'));
    expect(save().onPressed, isNull);

    await tester.tap(find.text('＋ 新相片冊'));
    await tester.pump();
    expect(save().onPressed, isNull);

    await tester.enterText(find.byType(TextField).last, '旅行');
    await tester.pump();
    expect(save().onPressed, isNotNull);
    await tester.tap(find.widgetWithText(FilledButton, '儲存'));
    await tester.pumpAndSettle();

    expect(result?.albumId, isNotNull);
    expect(repository.albums.single.name, '旅行');
  });
}
