import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 問題回報 #640 (owner chose A): photos still waiting for their safety
/// check — queued, no tagger, or tagging failed — show in the 相片冊; only
/// the ones the server rejects as unsafe (HTTP 451) never do.
void main() {
  Uint8List bytes(String s) => Uint8List.fromList(s.codeUnits);

  ({WordDatabaseRepository repo, PhotoIntake intake, TaggingQueue queue})
      setUp({int? status, bool configured = true}) {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: PhotoStore.inMemory(),
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((r) async =>
            http.Response('{"error":"rejected"}', status ?? 500)),
      ),
    );
    final queue = TaggingQueue(
        repository: () => repo,
        settings: configured
            ? AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k')
            : AppSettings.inMemory(),
        intake: intake,
        lexicon: testLexicon);
    return (repo: repo, intake: intake, queue: queue);
  }

  test('an unchecked photo is in the album grid and is its cover', () async {
    final s = setUp();
    final album = s.repo.addAlbum(name: '旅行');
    final photo =
        await s.intake.addPhoto(bytes('a'), title: '海邊', albumId: album.id);
    expect(photo.safetyStatus, PhotoSafetyStatus.unchecked);
    expect(s.repo.photos.map((p) => p.id), contains(photo.id));
    expect(s.repo.photosInAlbum(album.id).map((p) => p.id), [photo.id]);
    expect(s.repo.albumCoverPhoto(album.id)?.id, photo.id);
    expect(s.repo.photoCount, 1);
  });

  test('a photo whose tagging failed stays visible, still unchecked',
      () async {
    final s = setUp(status: 422);
    final album = s.repo.addAlbum(name: '旅行');
    final photo =
        await s.intake.addPhoto(bytes('a'), title: '海邊', albumId: album.id);
    await s.queue.process();
    final after = s.repo.photo(photo.id)!;
    expect(after.taggingStatus, TaggingStatus.failed);
    expect(after.safetyStatus, PhotoSafetyStatus.unchecked);
    expect(s.repo.albumCoverPhoto(album.id)?.id, photo.id);
  });

  test('a photo waiting for a tagger (none set up) stays visible', () async {
    final s = setUp(configured: false);
    final album = s.repo.addAlbum(name: '旅行');
    final photo =
        await s.intake.addPhoto(bytes('a'), title: '海邊', albumId: album.id);
    await s.queue.process();
    expect(s.repo.photo(photo.id)!.taggingStatus, TaggingStatus.pending);
    expect(s.repo.photosInAlbum(album.id).map((p) => p.id), [photo.id]);
    expect(s.repo.albumCoverPhoto(album.id)?.id, photo.id);
  });

  test('a photo the server rejects as unsafe (451) never shows', () async {
    final s = setUp(status: 451);
    final album = s.repo.addAlbum(name: '旅行');
    final photo =
        await s.intake.addPhoto(bytes('a'), title: '海邊', albumId: album.id);
    await s.queue.process();
    expect(s.repo.photo(photo.id), isNull);
    expect(s.repo.photos, isEmpty);
    expect(s.repo.allPhotos, isEmpty);
    expect(s.repo.photosInAlbum(album.id), isEmpty);
    expect(s.repo.albumCoverPhoto(album.id), isNull);
    expect(s.repo.reviewCoverPhoto(null), isNull);
  });
}
