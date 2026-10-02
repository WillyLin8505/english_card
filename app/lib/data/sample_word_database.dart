import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_detail.dart';
import '../models/word_entry.dart';
import '../services/cefr_lexicon.dart';
import '../services/tagging_service.dart';
import '../services/word_database_repository.dart';
import '../services/word_database_store.dart';
import 'sample_candidates.dart';

/// Sample content taken from the Figma mobile screens, seeded once on
/// first launch (until the camera/tagging flow has produced real data):
///
/// - photo-detail-view (24:4 / 54:77): the breakfast photo with the A1
///   words Coffee/Apple/Bread/Knife/Plate saved on it, pinned on the
///   objects; its candidate pool (real tagger output plus the mock's B1
///   words Espresso/Croissant/Utensil/Artisan/Ceramic) feeds the dial.
/// - camera-view (11:6): the kitchen photo, five of its six labels (a
///   photo keeps at most five words, spec section 7), and its pool.
/// - photo-album-page (17:5): the six albums and their covers.
/// - Project Photos · Mobile (39:65): six balcony photos (no image yet —
///   drawn as the mock's gradients) with their word chips.
/// - Word Database · Mobile (35:2): the eight balcony words and levels,
///   most recently updated first so page 1 matches the mock.
///
/// FSRS dates are relative to [now]; photo dates are the mock's.
WordDatabaseRepository sampleWordDatabase({
  DateTime? now,
  WordDetail? Function(String word)? lookupDetail,
  CefrLexicon? lexicon,
}) =>
    WordDatabaseRepository.fromData(
      sampleWordDatabaseData(now: now, lexicon: lexicon),
      lookupDetail: lookupDetail,
      clock: now != null ? () => now : DateTime.now,
    );

WordDatabaseData sampleWordDatabaseData({DateTime? now, CefrLexicon? lexicon}) {
  final t = now ?? DateTime.now();
  final lex = lexicon ?? CefrLexicon.instance;
  DateTime inDays(int d) => t.add(Duration(days: d));

  final entries = <String, WordEntry>{};
  var minutesAgo = 0;
  void word(
    String w,
    String pos,
    String zh,
    String level, {
    String? ipa,
    String? definitionZh,
    WordExample? example,
    List<RelatedWord> related = const [],
    List<WordForm> forms = const [],
    String? root,
    List<String> affixes = const [],
  }) {
    // Declaration order = 最近更新 order.
    minutesAgo += minutesAgo < 60 ? 5 : 60;
    entries[w] = WordEntry(
      id: 'w-${w.replaceAll(' ', '-')}',
      word: w,
      pos: pos,
      meaning: zh,
      definition: definitionZh,
      ipa: ipa,
      accent: ipa == null ? null : 'US',
      level: level,
      examples: [if (example != null) example],
      related: related,
      forms: forms,
      root: root,
      affixes: affixes,
      createdAt: inDays(-30),
      updatedAt: t.subtract(Duration(minutes: minutesAgo)),
    );
  }

  const syn = RelationType.synonym, assoc = RelationType.associated;
  RelatedWord r(String w, [RelationType type = syn]) => RelatedWord(w, type);

  // Word Database · Mobile, page 1, in the mock's order.
  word('balcony', 'noun', '陽台', 'A1',
      ipa: '/ˈbæl.kə.ni/',
      definitionZh: '陽台；建築物外牆突出、帶有欄杆的平台。',
      example: const WordExample(
          text: 'We had breakfast on the balcony.', translation: '我們在陽台上吃早餐。'),
      related: [r('terrace'), r('veranda'), r('railing', assoc)],
      forms: const [WordForm('balconies', '複數')]);
  word('dappled', 'adj.', '斑駁的', 'A2',
      ipa: '/ˈdæp.əld/',
      example: const WordExample(
          text: 'Dappled sunlight fell across the balcony floor.',
          translation: '斑駁的陽光灑落在陽台地板上。'),
      related: [r('mottled'), r('spotted')]);
  word('terrace', 'noun', '露台；平台', 'B1',
      ipa: '/ˈter.əs/',
      example: const WordExample(
          text: 'They grew tomatoes on the terrace.',
          translation: '他們在露台上種番茄。'),
      related: [r('balcony'), r('patio')],
      forms: const [WordForm('terraces', '複數')]);
  word('railing', 'noun', '欄杆；扶手', 'B1',
      ipa: '/ˈreɪ.lɪŋ/',
      example: const WordExample(
          text: 'She leaned on the railing.', translation: '她倚著欄杆。'),
      related: [r('handrail'), r('banister')],
      root: 'rail',
      affixes: const ['-ing']);
  word('sunlight', 'noun', '陽光', 'A1',
      ipa: '/ˈsʌn.laɪt/',
      // No translation on purpose — exercises 缺例句翻譯.
      example: const WordExample(text: 'The room was full of sunlight.'),
      related: [r('sunshine'), r('daylight')]);
  word('overlook', 'verb', '俯瞰；忽略', 'B2',
      ipa: '/ˌoʊ.vɚˈlʊk/',
      example: const WordExample(
          text: 'The balcony overlooks the park.', translation: '陽台俯瞰著公園。'),
      related: [
        r('survey'),
        r('ignore')
      ],
      forms: const [
        WordForm('overlooked', '過去式'),
        WordForm('overlooking', '進行式')
      ]);
  word('potted', 'adj.', '盆栽的', 'B1',
      ipa: '/ˈpɑː.t̬ɪd/',
      example: const WordExample(
          text: 'Potted herbs lined the windowsill.',
          translation: '窗台上擺滿了盆栽香草。'),
      related: [r('pot', RelationType.derivation), r('planted', assoc)]);
  word('breeze', 'noun', '微風', 'A2',
      // No IPA on purpose — exercises 缺音標.
      example: const WordExample(
          text: 'A cool breeze came through the door.',
          translation: '一陣涼爽的微風從門口吹進來。'),
      related: [r('wind'), r('gust')]);

  // photo-detail-view / camera-view words.
  word('coffee', 'noun', '咖啡', 'A1',
      ipa: '/ˈkɒf.i/',
      example: const WordExample(
          text: 'I drink coffee every morning.', translation: '我每天早上喝咖啡。'),
      related: [r('espresso', assoc), r('latte', assoc)]);
  word('apple', 'noun', '蘋果', 'A1',
      ipa: '/ˈæp.əl/',
      example: const WordExample(
          text: 'I eat an apple every day.', translation: '我每天吃一顆蘋果。'),
      related: [
        r('fruit', assoc),
        r('red delicious', assoc),
        r('gala', assoc),
        r('macintosh', assoc),
        r('apply', RelationType.similarSpelling),
        r('ample', RelationType.similarSpelling),
      ],
      forms: const [
        WordForm('apples', '複數')
      ]);
  word('bread', 'noun', '麵包', 'A1',
      ipa: '/ˈbred/',
      example: const WordExample(
          text: 'She bought a loaf of bread.', translation: '她買了一條麵包。'),
      related: [r('bred', RelationType.homophone), r('toast', assoc)]);
  word('knife', 'noun', '刀子', 'A1',
      ipa: '/naɪf/',
      example: const WordExample(
          text: 'Cut the bread with a knife.', translation: '用刀子切麵包。'),
      forms: const [WordForm('knives', '複數')]);
  word('plate', 'noun', '盤子', 'A1',
      ipa: '/pleɪt/',
      example: const WordExample(
          text: 'Put the toast on a plate.', translation: '把吐司放在盤子上。'),
      related: [r('dish'), r('plait', RelationType.homophone)]);
  word('cutting board', 'noun', '砧板', 'A2',
      ipa: '/ˈkʌt.ɪŋ ˌbɔːrd/',
      example: const WordExample(
          text: 'Chop the onions on the cutting board.',
          translation: '在砧板上切洋蔥。'));
  word('espresso', 'noun', '濃縮咖啡', 'B1',
      ipa: '/ɛˈsprɛsoʊ/',
      example: const WordExample(
          text: 'He ordered a double espresso.', translation: '他點了一杯雙份濃縮咖啡。'),
      related: [r('coffee', assoc)]);
  word('croissant', 'noun', '牛角麵包', 'B1',
      ipa: '/krwɑːˈsɒ̃/',
      example: const WordExample(
          text: 'A warm croissant with butter.',
          translation: '一個抹上奶油的溫熱牛角麵包。'));
  word('utensil', 'noun', '餐具', 'B1',
      ipa: '/juːˈtɛnsəl/',
      example: const WordExample(
          text: 'Keep the utensils in the drawer.', translation: '把餐具放在抽屜裡。'),
      forms: const [WordForm('utensils', '複數')]);
  word('artisan', 'adj.', '手工', 'B1',
      ipa: '/ˈɑːr.t̬ə.zən/',
      example: const WordExample(
          text: 'We bought artisan bread at the market.',
          translation: '我們在市集買了手工麵包。'));
  word('ceramic', 'adj.', '陶瓷', 'B1',
      ipa: '/səˈræm.ɪk/',
      example: const WordExample(
          text: 'The coffee came in a ceramic cup.', translation: '咖啡裝在陶瓷杯裡。'));

  // Other words on the 項目照片 cards.
  word('ocean', 'noun', '海洋', 'A1', ipa: '/ˈoʊ.ʃən/');
  word('wet', 'adj.', '潮濕的', 'A1', ipa: '/wet/');
  word('brick', 'noun', '磚塊', 'A2', ipa: '/brɪk/');
  word('shade', 'noun', '陰影；樹蔭', 'B1', ipa: '/ʃeɪd/');
  word('street', 'noun', '街道', 'A1', ipa: '/striːt/');
  word('garden', 'noun', '花園', 'A1', ipa: '/ˈɡɑːr.dən/');
  word('veranda', 'noun', '遊廊；陽台', 'B2', ipa: '/vəˈræn.də/');
  word('fruit', 'noun', '水果', 'A1', ipa: '/fruːt/');

  // Albums (photo-album-page), with the mock's covers.
  final albums = [
    for (final (i, (id, name, category, cover)) in const [
      ('album-kitchen', '廚房用品', '廚房', 'album_kitchen'),
      ('album-fruit', '水果與蔬菜', '食物', 'album_fruit'),
      ('album-office', '辦公室物品', null, 'album_office'),
      ('album-park', '公園散步', '戶外', 'album_park'),
      ('album-breakfast', '早餐時光', '食物', 'album_breakfast'),
      ('album-room', '我的房間', '客廳', 'album_room'),
      ('album-balcony', '陽台收藏', '戶外', null),
    ].indexed)
      Album(
        id: id,
        name: name,
        category: category,
        coverAsset: cover == null ? null : 'assets/sample/$cover.jpg',
        createdAt: inDays(-60 + i),
      ),
  ];

  final photos = <Photo>[];
  final occurrences = <PhotoOccurrence>[];
  final fsrsByWord = <String, FsrsState>{};

  void photo(
    String id,
    String title, {
    required String album,
    String? place,
    required DateTime takenAt,
    String? asset,
    (int, int)? size,
    List<int>? gradient,
    required List<(String word, double x, double y, FsrsState fsrs)> labels,
  }) {
    assert(labels.length <= 5, 'a photo keeps at most five words');
    final pool = sampleCandidates[id];
    photos.add(Photo(
      id: id,
      albumId: album,
      title: title,
      place: place,
      takenAt: takenAt,
      assetPath: asset == null ? null : 'assets/sample/$asset.jpg',
      placeholderColors: gradient,
      width: size?.$1,
      height: size?.$2,
      createdAt: takenAt,
      taggingStatus: TaggingStatus.done,
      candidates: pool == null
          ? const []
          : parseCandidates({'candidates': pool}, lexicon: lex),
      wordsSavedAt: takenAt,
    ));
    for (final (w, x, y, fsrs) in labels) {
      final entry = entries[w]!;
      occurrences.add(PhotoOccurrence(
        id: '$id:${entry.id}',
        photoId: id,
        wordEntryId: entry.id,
        anchor: LabelPoint(x, y),
        aiLabel: w,
      ));
      // One card per word; the most-reviewed state wins.
      final had = fsrsByWord[entry.id];
      if (had == null || fsrs.reps > had.reps) fsrsByWord[entry.id] = fsrs;
    }
  }

  FsrsState learning(double stability, int dueInDays) => FsrsState(
        state: FsrsCardState.learning,
        stability: stability,
        difficulty: 5.2,
        due: inDays(dueInDays),
        lastReview: inDays(-1),
        reps: 2,
      );
  FsrsState review(double stability, int dueInDays) => FsrsState(
        state: FsrsCardState.review,
        stability: stability,
        difficulty: 4.6,
        due: inDays(dueInDays),
        lastReview: inDays(dueInDays - stability.round()),
        reps: 5,
      );
  const fresh = FsrsState.initial;

  // Anchors are where each object actually is, as fractions of the
  // original image (the spec's 標籤座標). The mock's pins are laid out
  // for looks and don't sit on their objects (its "Apple" pin is on the
  // saucer), so labels here land where the mock's don't.
  photo('photo-breakfast', '早餐桌',
      album: 'album-breakfast',
      place: '家裡餐桌',
      takenAt: DateTime(2026, 9, 20, 8, 12),
      asset: 'photo_breakfast',
      size: (
        1152,
        928
      ),
      labels: [
        ('coffee', 0.729, 0.345, fresh),
        ('apple', 0.241, 0.496, fresh),
        ('bread', 0.460, 0.590, fresh),
        ('knife', 0.640, 0.640, fresh),
        ('plate', 0.470, 0.745, fresh),
      ]);
  photo('photo-kitchen', '廚房早晨',
      album: 'album-kitchen',
      place: '家裡廚房',
      takenAt: DateTime(2026, 9, 22, 7, 40),
      asset: 'photo_kitchen',
      size: (
        896,
        1200
      ),
      labels: [
        ('bread', 0.446, 0.683, fresh),
        ('cutting board', 0.520, 0.850, fresh),
        ('apple', 0.140, 0.633, fresh),
        ('coffee', 0.513, 0.408, fresh),
        ('knife', 0.368, 0.550, fresh),
      ]);

  // Project Photos · Mobile — the six balcony photos, newest first.
  photo('photo-morning-balcony', '晨光陽台',
      album: 'album-balcony',
      place: '台北住家',
      takenAt: DateTime(2026, 9, 12),
      gradient: const [
        0xFF2E426B,
        0xFF9E704F
      ],
      labels: [
        ('balcony', 0.5, 0.55, learning(6.4, 0)),
        ('sunlight', 0.3, 0.25, fresh),
        ('railing', 0.7, 0.7, learning(2.1, 0)),
        ('dappled', 0.22, 0.8, review(12, 1)),
      ]);
  photo('photo-sea-hotel', '海景旅館',
      album: 'album-balcony',
      place: '沖繩旅行',
      takenAt: DateTime(2026, 7, 28),
      gradient: const [
        0xFF1A5C7A,
        0xFF5CA6B8
      ],
      labels: [
        ('balcony', 0.45, 0.6, fresh),
        ('ocean', 0.7, 0.3, fresh),
        ('breeze', 0.25, 0.35, review(10, 3)),
        ('overlook', 0.6, 0.8, review(7, 2)),
      ]);
  photo('photo-after-rain', '雨後下午',
      album: 'album-balcony',
      place: '日常散步',
      takenAt: DateTime(2026, 6, 3),
      gradient: const [
        0xFF334D47,
        0xFF61826B
      ],
      labels: [
        ('balcony', 0.5, 0.5, fresh),
        ('potted', 0.25, 0.7, review(40, 8)),
        ('wet', 0.7, 0.3, fresh),
      ]);
  photo('photo-old-terrace', '老城露台',
      album: 'album-balcony',
      place: '台南週末',
      takenAt: DateTime(2026, 3, 19),
      gradient: const [
        0xFF704033,
        0xFFB88057
      ],
      labels: [
        ('balcony', 0.4, 0.55, fresh),
        ('brick', 0.7, 0.75, fresh),
        ('shade', 0.25, 0.3, fresh),
        ('terrace', 0.65, 0.35, review(30, 4)),
      ]);
  photo('photo-cafe', '咖啡館二樓',
      album: 'album-balcony',
      place: '城市收藏',
      takenAt: DateTime(2026, 1, 8),
      gradient: const [
        0xFF382B47,
        0xFF80598C
      ],
      labels: [
        ('balcony', 0.5, 0.45, fresh),
        ('coffee', 0.3, 0.7, fresh),
        ('street', 0.7, 0.8, fresh),
      ]);
  photo('photo-garden-inn', '花園民宿',
      album: 'album-balcony',
      place: '花蓮旅行',
      takenAt: DateTime(2025, 11, 22),
      gradient: const [
        0xFF295740,
        0xFF7AA661
      ],
      labels: [
        ('balcony', 0.5, 0.5, fresh),
        ('garden', 0.3, 0.75, fresh),
        ('veranda', 0.7, 0.35, fresh),
      ]);

  // Words not on any photo (the mock's B1 labels live in the breakfast
  // pool now) aren't part of the sample.
  final used = {for (final o in occurrences) o.wordEntryId};
  return WordDatabaseData(
    entries: [
      for (final e in entries.values)
        if (used.contains(e.id)) e,
    ],
    photos: photos,
    albums: albums,
    occurrences: occurrences,
    cards: [
      for (final e in fsrsByWord.entries)
        LearningCard(
          id: LearningCard.idFor(e.key),
          wordEntryId: e.key,
          templateId: 'photo-word-card',
          fsrs: e.value,
          createdAt: inDays(-30),
          updatedAt: inDays(-1),
        ),
    ],
  );
}
