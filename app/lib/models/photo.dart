/// Spec section 3's Photo entity plus the albums the 相片冊 tab groups
/// photos into.
library;

import 'word_candidate.dart';

/// Where a photo is in the AI tagging pipeline (spec section 7, 非同步辨識
/// 與連線): [pending] photos wait in the local queue — the 相片冊 shows
/// an hourglass on them — and are tagged in the background whenever the
/// tagger is reachable again; nobody is notified.
enum TaggingStatus { none, pending, tagging, done, failed }

/// Where a photo's pixels live. Exactly one of these is set, checked in
/// this order by PhotoImage:
/// - [assetPath]: a bundled sample photo;
/// - [filePath]: the original on the device (mobile/desktop);
/// - [storedKey]: bytes kept in the app's local store (web, where there
///   is no file system);
/// - [placeholderColors]: no image yet — a two-colour gradient, as the
///   Figma 項目照片 cards show.
class Photo {
  final String id;
  final String? albumId;

  /// Name shown on photo cards ("晨光陽台").
  final String title;

  /// Where/which trip it's from ("台北住家").
  final String? place;
  final DateTime takenAt;

  final String? assetPath;
  final String? filePath;
  final String? storedKey;

  /// A picture on the word-database server (the database album). Views
  /// only: never saved with the learner's photos.
  final String? networkUrl;
  final List<int>? placeholderColors;

  /// Pixel size of the original (spec: 尺寸). Label anchors are fractions
  /// of the original image, so views that crop it need this to place
  /// pins; null when unknown (placeholders).
  final int? width;
  final int? height;

  final DateTime createdAt;

  final TaggingStatus taggingStatus;

  /// Why the last tagging attempt failed, for the photo-detail screen.
  final String? taggingError;

  /// The stage-1 candidate pool (spec section 3). The difficulty dial
  /// picks from it without calling the model again.
  final List<WordCandidate> candidates;

  /// The dial's position for this photo, relative to the learner's level
  /// (spec: 輪盤選擇只保存為此照片的 difficultyOffset — it never changes
  /// the learner's overall level).
  final int difficultyOffset;

  /// When the photo's word list was first saved (leaving 照片詳情). Until
  /// then the list is picked fresh from [candidates].
  final DateTime? wordsSavedAt;

  const Photo({
    required this.id,
    this.albumId,
    required this.title,
    this.place,
    required this.takenAt,
    this.assetPath,
    this.filePath,
    this.storedKey,
    this.networkUrl,
    this.placeholderColors,
    this.width,
    this.height,
    required this.createdAt,
    this.taggingStatus = TaggingStatus.none,
    this.taggingError,
    this.candidates = const [],
    this.difficultyOffset = 0,
    this.wordsSavedAt,
  });

  bool get hasImage =>
      assetPath != null || filePath != null || storedKey != null || networkUrl != null;

  /// Shown with an hourglass: waiting for (or in) AI tagging.
  bool get awaitingTagging =>
      taggingStatus == TaggingStatus.pending ||
      taggingStatus == TaggingStatus.tagging;

  Photo copyWith({
    String? Function()? albumId,
    String? title,
    String? Function()? place,
    TaggingStatus? taggingStatus,
    String? Function()? taggingError,
    List<WordCandidate>? candidates,
    int? difficultyOffset,
    DateTime? wordsSavedAt,
  }) =>
      Photo(
        id: id,
        albumId: albumId != null ? albumId() : this.albumId,
        title: title ?? this.title,
        place: place != null ? place() : this.place,
        takenAt: takenAt,
        assetPath: assetPath,
        filePath: filePath,
        storedKey: storedKey,
        placeholderColors: placeholderColors,
        width: width,
        height: height,
        createdAt: createdAt,
        taggingStatus: taggingStatus ?? this.taggingStatus,
        taggingError: taggingError != null ? taggingError() : this.taggingError,
        candidates: candidates ?? this.candidates,
        difficultyOffset: difficultyOffset ?? this.difficultyOffset,
        wordsSavedAt: wordsSavedAt ?? this.wordsSavedAt,
      );

  factory Photo.fromJson(Map<String, dynamic> j) => Photo(
        id: j['id'] as String,
        albumId: j['albumId'] as String?,
        title: j['title'] as String,
        place: j['place'] as String?,
        takenAt: DateTime.parse(j['takenAt'] as String),
        assetPath: j['assetPath'] as String?,
        filePath: j['filePath'] as String?,
        storedKey: j['storedKey'] as String?,
        placeholderColors: (j['placeholderColors'] as List?)?.cast<int>(),
        width: j['width'] as int?,
        height: j['height'] as int?,
        createdAt: DateTime.parse(j['createdAt'] as String),
        taggingStatus: TaggingStatus.values.asNameMap()[j['taggingStatus']] ??
            TaggingStatus.none,
        taggingError: j['taggingError'] as String?,
        candidates: [
          for (final c in (j['candidates'] as List? ?? const []))
            WordCandidate.fromJson(c as Map<String, dynamic>),
        ],
        difficultyOffset: j['difficultyOffset'] as int? ?? 0,
        wordsSavedAt: j['wordsSavedAt'] == null
            ? null
            : DateTime.parse(j['wordsSavedAt'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'albumId': albumId,
        'title': title,
        'place': place,
        'takenAt': takenAt.toIso8601String(),
        'assetPath': assetPath,
        'filePath': filePath,
        'storedKey': storedKey,
        'placeholderColors': placeholderColors,
        'width': width,
        'height': height,
        'createdAt': createdAt.toIso8601String(),
        'taggingStatus': taggingStatus.name,
        'taggingError': taggingError,
        'candidates': [for (final c in candidates) c.toJson()],
        'difficultyOffset': difficultyOffset,
        'wordsSavedAt': wordsSavedAt?.toIso8601String(),
      };
}

/// The 相片冊 filter pills (Figma photo-album-page, 17:19).
const albumCategories = ['廚房', '客廳', '戶外', '食物', '動物'];

class Album {
  final String id;
  final String name;

  /// One of [albumCategories], or null for none.
  final String? category;

  /// Bundled cover for sample albums; user albums use their newest photo.
  final String? coverAsset;
  final DateTime createdAt;

  const Album({
    required this.id,
    required this.name,
    this.category,
    this.coverAsset,
    required this.createdAt,
  });

  factory Album.fromJson(Map<String, dynamic> j) => Album(
        id: j['id'] as String,
        name: j['name'] as String,
        category: j['category'] as String?,
        coverAsset: j['coverAsset'] as String?,
        createdAt: DateTime.parse(j['createdAt'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'category': category,
        'coverAsset': coverAsset,
        'createdAt': createdAt.toIso8601String(),
      };
}
