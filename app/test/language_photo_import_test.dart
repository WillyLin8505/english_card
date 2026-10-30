import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/language_photo_import.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

import 'helpers.dart';

/// Owner 2026-10-30: 「把目前語言的照片一鍵匯入到新語言，用新語言重新辨識
/// 標籤，單字本不搬」.
final _a = Uint8List.fromList(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAEElEQVR4nGNocFCAIwacHADRZwqBZaYHGAAAAABJRU5ErkJggg=='));
final _b = Uint8List.fromList(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='));

void main() {
  testWidgets('own photos come over, recognized again; words stay',
      (tester) async {
    final store = PhotoStore.inMemory();
    final en = WordDatabaseRepository.fromData(const WordDatabaseData(),
        clock: () => testNow);
    final enIntake = PhotoIntake(repository: () => en, photoStore: store);
    final album = en.addAlbum(name: 'rrr');
    final deck = en.addAlbum(name: 'Fruit deck', deckSlug: 'fruit');
    await tester.runAsync(() async {
      await enIntake.addPhoto(_a, title: 'lamp', albumId: album.id);
      await enIntake.addPhoto(_b, title: 'desk');
    });
    final lamp = en.photos.firstWhere((p) => p.title == 'lamp');
    en.updatePhoto(lamp.copyWith(
        taggingStatus: TaggingStatus.done,
        candidates: const [
          WordCandidate(
              word: 'lightbulb',
              pos: 'noun',
              meaning: '燈泡',
              level: 'B1',
              levelSource: 'cefr-j',
              point: LabelPoint(0.5, 0.5)),
        ]));
    en.addWord(word: 'lightbulb', pos: 'noun', meaning: '燈泡');
    en.addPhoto(Photo(
        id: 'photo-deck-1',
        albumId: deck.id,
        title: 'apple',
        takenAt: testNow,
        createdAt: testNow,
        networkUrl: 'https://example.com/apple.jpg'));

    final source = ImportSource.of(
        WordDatabaseData(photos: en.photos, albums: en.albums));
    expect(source.photos.map((p) => p.title), unorderedEquals(['lamp', 'desk']));

    final fr = WordDatabaseRepository.fromData(const WordDatabaseData(),
        language: 'fr', clock: () => testNow);
    final frIntake = PhotoIntake(repository: () => fr, photoStore: store);
    final added = await tester
        .runAsync(() => LanguagePhotoImport.copy(source, fr, frIntake));
    expect(added, 2);
    expect(fr.photos.map((p) => p.title), unorderedEquals(['lamp', 'desk']));
    // Recognized again in French: no labels yet, waiting for the AI.
    for (final p in fr.photos) {
      expect(p.candidates, isEmpty);
      expect(p.taggingStatus, TaggingStatus.pending);
    }
    // The same album name, made in French; the deck is not brought over.
    final frLamp = fr.photos.firstWhere((p) => p.title == 'lamp');
    expect(fr.album(frLamp.albumId!)?.name, 'rrr');
    expect(fr.albums.map((a) => a.name), ['rrr']);
    // The 單字本 stays in English.
    expect(fr.entries, isEmpty);
    expect(en.entryByWord('lightbulb'), isNotNull);

    // A second tap adds nothing.
    final again = await tester
        .runAsync(() => LanguagePhotoImport.copy(source, fr, frIntake));
    expect(again, 0);
    expect(fr.photos, hasLength(2));
  });
}
