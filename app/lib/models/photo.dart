/// Spec section 3's Photo entity plus the albums the 相片冊 tab groups
/// photos into.
library;

import 'word_candidate.dart';

/// Where a photo is in the AI tagging pipeline (spec section 7, 非同步辨識
/// 與連線): [pending] photos wait in the local queue — the 相片冊 shows
/// an hourglass on them — and are tagged in the background whenever the
/// tagger is reachable again; nobody is notified.
enum TaggingStatus { none, pending, tagging, done, failed }

/// New user photos start [unchecked] until the combined safety and label
/// pass accepts them; they are shown in the 相片冊 meanwhile (問題回報
/// #640). A photo the server rejects as unsafe (HTTP 451) is deleted, not
/// kept with a status. Legacy and bundled photos default to safe.
enum PhotoSafetyStatus { unchecked, safe }

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
  final PhotoSafetyStatus safetyStatus;

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

  /// Hash of the picture's bytes (see [PhotoIntake.hashBytes]), so adding
  /// the same picture twice can be noticed (spec §7: 重複加入同一照片 was
  /// deferred for MVP; card #217). Null for bundled samples and photos
  /// saved before the hash existed — those are never reported as duplicates.
  final String? contentHash;

  /// What recognition looks for (問題回報 #324): things in the picture,
  /// printed English text (signs, menus, book pages), or both.
  final PhotoScanMode scanMode;

  /// Words the learner said are not in this photo: labels deleted as wrong
  /// and AI labels they corrected to another word (問題回報 #323). The
  /// difficulty dial and background top-ups never offer them again.
  final List<String> rejectedWords;

  /// Author and licence of a deck picture (問題回報 #329), e.g.
  /// "Jane Doe · CC BY 4.0 · https://…". Null for the learner's own photos.
  final String? credit;

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
    this.safetyStatus = PhotoSafetyStatus.safe,
    this.taggingError,
    this.candidates = const [],
    this.difficultyOffset = 0,
    this.wordsSavedAt,
    this.contentHash,
    this.scanMode = PhotoScanMode.objects,
    this.rejectedWords = const [],
    this.credit,
  });

  bool get hasImage =>
      assetPath != null ||
      filePath != null ||
      storedKey != null ||
      networkUrl != null;

  /// Shown with an hourglass: waiting for (or in) AI tagging.
  bool get awaitingTagging =>
      taggingStatus == TaggingStatus.pending ||
      taggingStatus == TaggingStatus.tagging;

  Photo copyWith({
    String? Function()? albumId,
    String? title,
    String? Function()? place,
    TaggingStatus? taggingStatus,
    PhotoSafetyStatus? safetyStatus,
    String? Function()? taggingError,
    List<WordCandidate>? candidates,
    int? difficultyOffset,
    DateTime? wordsSavedAt,
    List<String>? rejectedWords,
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
        networkUrl: networkUrl,
        placeholderColors: placeholderColors,
        width: width,
        height: height,
        createdAt: createdAt,
        taggingStatus: taggingStatus ?? this.taggingStatus,
        safetyStatus: safetyStatus ?? this.safetyStatus,
        taggingError: taggingError != null ? taggingError() : this.taggingError,
        candidates: candidates ?? this.candidates,
        difficultyOffset: difficultyOffset ?? this.difficultyOffset,
        wordsSavedAt: wordsSavedAt ?? this.wordsSavedAt,
        contentHash: contentHash,
        scanMode: scanMode,
        rejectedWords: rejectedWords ?? this.rejectedWords,
        credit: credit,
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
        safetyStatus: PhotoSafetyStatus.values.asNameMap()[j['safetyStatus']] ??
            PhotoSafetyStatus.safe,
        taggingError: j['taggingError'] as String?,
        candidates: [
          for (final c in (j['candidates'] as List? ?? const []))
            WordCandidate.fromJson(c as Map<String, dynamic>),
        ],
        difficultyOffset: j['difficultyOffset'] as int? ?? 0,
        wordsSavedAt: j['wordsSavedAt'] == null
            ? null
            : DateTime.parse(j['wordsSavedAt'] as String),
        contentHash: j['contentHash'] as String?,
        scanMode: PhotoScanMode.values.asNameMap()[j['scanMode']] ??
            PhotoScanMode.objects,
        rejectedWords:
            (j['rejectedWords'] as List?)?.cast<String>() ?? const [],
        credit: j['credit'] as String?,
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
        'safetyStatus': safetyStatus.name,
        'taggingError': taggingError,
        'candidates': [for (final c in candidates) c.toJson()],
        'difficultyOffset': difficultyOffset,
        'wordsSavedAt': wordsSavedAt?.toIso8601String(),
        'contentHash': contentHash,
        if (scanMode != PhotoScanMode.objects) 'scanMode': scanMode.name,
        if (rejectedWords.isNotEmpty) 'rejectedWords': rejectedWords,
        if (credit != null) 'credit': credit,
      };
}

/// 找物品／找文字／兩者都找 (問題回報 #324).
enum PhotoScanMode {
  objects('找物品'),
  text('找文字'),
  both('兩者都找');

  final String label;
  const PhotoScanMode(this.label);

  bool get findsObjects => this != text;
  bool get findsText => this != objects;
}

/// Scenes the 相片冊 groups albums by (問題回報 #404): no fixed list of
/// pills — a group exists only when some album's recognised words point to
/// it. Words (lower-case English lemmas) that hint at each scene.
const albumSceneWords = <String, Set<String>>{
  '廚房': {
    'kitchen',
    'cup',
    'bowl',
    'knife',
    'fork',
    'spoon',
    'plate',
    'pan',
    'pot',
    'stove',
    'oven',
    'fridge',
    'refrigerator',
    'kettle',
    'mug',
    'sink',
    'microwave',
    'toaster'
  },
  '客廳': {
    'sofa',
    'couch',
    'tv',
    'television',
    'lamp',
    'table',
    'chair',
    'carpet',
    'rug',
    'curtain',
    'shelf',
    'bed',
    'pillow',
    'clock'
  },
  '戶外': {
    'tree',
    'street',
    'road',
    'car',
    'bus',
    'bicycle',
    'bike',
    'building',
    'sky',
    'cloud',
    'mountain',
    'river',
    'bridge',
    'flower',
    'grass',
    'sun',
    'traffic'
  },
  '食物': {
    'apple',
    'banana',
    'bread',
    'cake',
    'pizza',
    'rice',
    'noodle',
    'egg',
    'fruit',
    'vegetable',
    'meat',
    'coffee',
    'tea',
    'sandwich',
    'orange',
    'food',
    'cookie',
    'soup'
  },
  '動物': {
    'dog',
    'cat',
    'bird',
    'fish',
    'horse',
    'cow',
    'rabbit',
    'animal',
    'duck',
    'chicken',
    'pig',
    'sheep',
    'butterfly',
    'insect'
  },
};

/// 圖片集 albums (downloaded 卡片集) sit under this group.
const deckAlbumGroup = '圖片集';

class Album {
  final String id;
  final String name;

  /// One of [albumCategories], or null for none.
  final String? category;

  /// Bundled cover for sample albums; user albums use their newest photo.
  final String? coverAsset;
  final DateTime createdAt;

  /// Set for the album of a downloaded 卡片集 picture deck (問題回報 #403):
  /// its slug, and the author the deck names.
  final String? deckSlug;
  final String? author;

  const Album({
    required this.id,
    required this.name,
    this.category,
    this.coverAsset,
    required this.createdAt,
    this.deckSlug,
    this.author,
  });

  factory Album.fromJson(Map<String, dynamic> j) => Album(
        id: j['id'] as String,
        name: j['name'] as String,
        category: j['category'] as String?,
        coverAsset: j['coverAsset'] as String?,
        createdAt: DateTime.parse(j['createdAt'] as String),
        deckSlug: j['deckSlug'] as String?,
        author: j['author'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'category': category,
        'coverAsset': coverAsset,
        'createdAt': createdAt.toIso8601String(),
        'deckSlug': deckSlug,
        'author': author,
      };
}
