import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

void main() {
  testWidgets('a photo cannot be saved until an album is selected or named',
      (tester) async {
    final repository = WordDatabaseRepository();
    ({String title, String? albumId})? result;
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
