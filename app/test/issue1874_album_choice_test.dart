import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

/// 問題回報 #1874: after a photo is saved (recognition already running) the
/// learner picks the 相片冊 it goes in; keeping the album leaves it be.
Photo _photo(String id, String albumId) => Photo(
      id: id,
      albumId: albumId,
      title: '10/19 14:32',
      takenAt: DateTime(2026, 10, 19, 14, 32),
      createdAt: DateTime(2026, 10, 19, 14, 32),
      taggingStatus: TaggingStatus.pending,
      safetyStatus: PhotoSafetyStatus.unchecked,
      scanMode: PhotoScanMode.both,
    );

void main() {
  late WordDatabaseRepository repository;
  late String first;
  late String second;

  setUp(() {
    repository = WordDatabaseRepository();
    first = repository.addAlbum(name: '我的照片').id;
    second = repository.addAlbum(name: '旅行').id;
    repository.addPhoto(_photo('photo-1', first));
  });

  /// Opens the dialog the way the camera and picker do, then picks [tapText]
  /// (an album name or the keep button) and returns after it closes.
  Future<void> answer(WidgetTester tester, String tapText) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) {
        return FilledButton(
          onPressed: () => askAlbumForPhotos(context, repository, ['photo-1'],
              albumId: first),
          child: const Text('開啟'),
        );
      }),
    ));
    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(tapText));
    await tester.pumpAndSettle();
  }

  testWidgets('the album picked after the save takes the photo', (tester) async {
    await answer(tester, '旅行');
    await tester.tap(find.widgetWithText(FilledButton, '儲存'));
    await tester.pumpAndSettle();

    expect(repository.photo('photo-1')?.albumId, second);
  });

  testWidgets('keeping the album leaves the photo where it is', (tester) async {
    await answer(tester, '留在這裡');

    expect(repository.photo('photo-1')?.albumId, first);
  });

  test('a named album is the default; no albums means no default', () {
    expect(defaultSaveAlbumId(repository, albumId: second), second);
    expect(defaultSaveAlbumId(WordDatabaseRepository()), isNull);
  });
}
