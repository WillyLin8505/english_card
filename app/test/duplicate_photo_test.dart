import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

import 'helpers.dart';

/// 重複加入同一照片 (spec §7 deferred item, card #217): the same bytes
/// again are noticed; the learner may open the existing photo or insist.
void main() {
  Uint8List bytes(String s) => Uint8List.fromList(s.codeUnits);

  test('hashBytes is stable and tells different pictures apart', () {
    expect(PhotoIntake.hashBytes(bytes('photo-1')),
        PhotoIntake.hashBytes(bytes('photo-1')));
    expect(PhotoIntake.hashBytes(bytes('photo-1')),
        isNot(PhotoIntake.hashBytes(bytes('photo-2'))));
    expect(PhotoIntake.hashBytes(Uint8List(0)), isNotEmpty);
  });

  test('addPhoto stores the hash; findDuplicate finds it, even unchecked',
      () async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final intake =
        PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory());
    expect(intake.findDuplicate(bytes('same')), isNull);
    final photo = await intake.addPhoto(bytes('same'), title: '第一張');
    expect(photo.contentHash, PhotoIntake.hashBytes(bytes('same')));
    // Still awaiting its safety check — not in repo.photos yet.
    expect(photo.safetyStatus, PhotoSafetyStatus.unchecked);
    expect(intake.findDuplicate(bytes('same'))?.id, photo.id);
    expect(intake.findDuplicate(bytes('other')), isNull);
  });

  test('photos saved before the hash existed never count as duplicates',
      () async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final intake =
        PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory());
    final old = Photo.fromJson({
      'id': 'old',
      'title': '舊照片',
      'takenAt': testNow.toIso8601String(),
      'createdAt': testNow.toIso8601String(),
      'storedKey': 'old',
    });
    expect(old.contentHash, isNull);
    repo.addPhoto(old);
    expect(intake.findDuplicate(bytes('anything')), isNull);
    // The hash survives a JSON round trip and copyWith.
    final fresh = await intake.addPhoto(bytes('x'), title: 'x');
    final back = Photo.fromJson(fresh.toJson());
    expect(back.contentHash, fresh.contentHash);
    expect(fresh.copyWith(title: 'y').contentHash, fresh.contentHash);
  });

  testWidgets('the duplicate dialog offers the existing photo or adding anyway',
      (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final album = repo.addAlbum(name: '早餐');
    final intake =
        PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory());
    final existing =
        await intake.addPhoto(bytes('same'), title: '週日早餐', albumId: album.id);
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) {
        return FilledButton(
          onPressed: () async {
            result = await showDuplicatePhotoDialog(context,
                existing: existing, repository: repo);
          },
          child: const Text('開啟'),
        );
      }),
    ));

    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    expect(find.text('這張照片已經加入過'), findsOneWidget);
    expect(find.textContaining('相片冊「早餐」的「週日早餐」'), findsOneWidget);
    await tester.tap(find.text('打開原本的照片'));
    await tester.pumpAndSettle();
    expect(result, isFalse);

    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('仍要再加入'));
    await tester.pumpAndSettle();
    expect(result, isTrue);

    // Dismissed (tap outside): null, so the picker does nothing.
    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(result, isNull);
  });
}
