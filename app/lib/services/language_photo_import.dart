import '../models/photo.dart';
import 'photo_intake.dart';
import 'word_database_repository.dart';
import 'word_database_store.dart';

/// Owner 2026-10-30: each learning language has its own 相片冊, labels and
/// 單字本, so a new language starts empty. One tap brings the learner's own
/// photos over from another learning language: the same pictures, in
/// albums of the same names, recognized again in the new language. The
/// 單字本, cards and review history stay where they are.
class LanguagePhotoImport {
  LanguagePhotoImport._();

  /// The learner's own photos saved for [language] — not 卡片集 or
  /// word-database pictures — with the names of their albums.
  static Future<ImportSource> load(String language) async {
    final data = (await HiveWordDatabaseStore.open(language: language)).load();
    return ImportSource.of(data);
  }

  /// Copies [source]'s photos into [repo] through [intake], as new photos
  /// waiting for recognition. A picture [repo] already has (same bytes) is
  /// skipped, so a second tap adds nothing. Returns how many were added.
  static Future<int> copy(ImportSource source, WordDatabaseRepository repo,
      PhotoIntake intake) async {
    final albums = <String, String>{
      for (final a in repo.albums)
        if (a.deckSlug == null) a.name: a.id,
    };
    var added = 0;
    for (final p in source.photos) {
      final bytes = await intake.bytesOf(p);
      if (bytes == null || intake.findDuplicate(bytes) != null) continue;
      final name = source.albumNames[p.albumId];
      String? albumId;
      if (name != null) {
        albumId = albums[name] ??= repo.addAlbum(name: name).id;
      }
      await intake.addPhoto(bytes,
          title: p.title, albumId: albumId, place: p.place);
      added++;
    }
    return added;
  }
}

/// What another learning language has to bring over.
class ImportSource {
  final List<Photo> photos;

  /// Album id → name, for the learner's own albums.
  final Map<String, String> albumNames;

  const ImportSource(this.photos, this.albumNames);

  factory ImportSource.of(WordDatabaseData data) {
    final decks = {
      for (final a in data.albums)
        if (a.deckSlug != null) a.id
    };
    return ImportSource([
      for (final p in data.photos)
        if (_own(p, decks)) p
    ], {
      for (final a in data.albums)
        if (a.deckSlug == null) a.id: a.name
    });
  }

  /// Same test as [WordDatabaseRepository.isOwnPhoto], on stored data.
  static bool _own(Photo p, Set<String> deckAlbums) =>
      !p.id.startsWith('db-') &&
      !p.id.startsWith('photo-deck-') &&
      p.networkUrl == null &&
      p.credit == null &&
      p.assetPath == null &&
      (p.filePath != null || p.storedKey != null) &&
      !deckAlbums.contains(p.albumId);
}
