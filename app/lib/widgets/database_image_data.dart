part of '../screens/database_library_screen.dart';

/// Pictures this entry shows, using the pack's picture_ids (the same rule
/// as the missing-picture count and the fetch queue).
List<Map<String, dynamic>> databaseEntryImages(
    List<Map<String, dynamic>> catalog, LexEntry word) {
  if (word.pictureIds != null && word.pictureIds!.isEmpty) return const [];
  final ids = (word.pictureIds ?? [word.id]).toSet();
  return [
    for (final image in catalog)
      if (databaseImageTags(image).any((tag) =>
          ids.contains((tag['lexeme_id'] as num?)?.toInt())))
        image
  ];
}

/// Approved tags, one per word sense: a sense remap can leave the same
/// lexeme + sense twice on a picture, which listed the word twice (卡 #225).
List<Map<String, dynamic>> databaseImageTags(Map<String, dynamic> image) {
  final seen = <(Object?, Object?)>{};
  return [
    for (final tag in (image['tags'] as List? ?? []))
      if ((tag as Map)['review_status'] == 'approved' &&
          seen.add((tag['lexeme_id'], tag['sense_id'])))
        Map<String, dynamic>.from(tag)
  ];
}

String databaseTagLabel(Map<String, dynamic> tag, LexiconPack pack) {
  final word = pack.byId((tag['lexeme_id'] as num).toInt());
  if (word == null) return '單字待補齊';
  final sense = word.senses.where((s) => s.id == tag['sense_id']).firstOrNull;
  return '${word.lemma} · ${sense?.native ?? word.nativeMeaning ?? '{N}意思待補齊'}';
}

String databaseImageLabels(Map<String, dynamic> image, LexiconPack pack) =>
    databaseImageTags(image)
        .map((tag) => databaseTagLabel(tag, pack))
        .toSet()
        .join('、');

final _searchWordBreak = RegExp(r'[\s\-–—/、，,；;：:（）()「」]+');

/// How [query] matches a tag (問題回報 #396 decision): 0 = a whole word or
/// meaning, 1 = the start of one (cat → cats, catch), null = no match —
/// letters inside a word (category, scatter) don't count.
int? databaseTagMatch(
    Map<String, dynamic> tag, LexiconPack pack, String query) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return 0;
  final word = pack.byId((tag['lexeme_id'] as num).toInt());
  if (word == null) return null;
  final sense = word.senses.where((s) => s.id == tag['sense_id']).firstOrNull;
  int? best;
  for (final text in [word.lemma, sense?.native ?? word.nativeMeaning ?? '']) {
    final t = text.trim().toLowerCase();
    for (final part in [t, ...t.split(_searchWordBreak)]) {
      if (part == q) return 0;
      if (part.startsWith(q)) best = 1;
    }
  }
  return best;
}

/// The best [databaseTagMatch] among the picture's tags.
int? databaseImageMatch(
    Map<String, dynamic> image, LexiconPack pack, String query) {
  int? best;
  for (final tag in databaseImageTags(image)) {
    final m = databaseTagMatch(tag, pack, query);
    if (m != null && (best == null || m < best)) best = m;
    if (best == 0) break;
  }
  return best;
}

/// The searched words on this picture and their levels (A1→C2, unleveled
/// last as null). Search spans every level while the album shows one, so the
/// hit can sit at a level the learner isn't looking at (問題回報 #302).
/// Whole-word hits come before words that only start with the query (#396).
List<(String word, String? level)> databaseSearchHits(
    Map<String, dynamic> image, LexiconPack pack, String query) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return const [];
  final matches = <(String, String?), int>{};
  for (final tag in databaseImageTags(image)) {
    final m = databaseTagMatch(tag, pack, q);
    if (m == null) continue;
    final key = (
      pack.byId((tag['lexeme_id'] as num).toInt())?.lemma ?? query.trim(),
      databaseTagLevel(tag, pack)
    );
    final seen = matches[key];
    if (seen == null || m < seen) matches[key] = m;
  }
  int rank(String? l) => l == null ? cefrLevels.length : cefrLevels.indexOf(l);
  return matches.keys.toList()
    ..sort((a, b) {
      final byMatch = matches[a]!.compareTo(matches[b]!);
      return byMatch != 0 ? byMatch : rank(a.$2).compareTo(rank(b.$2));
    });
}

/// The level to switch to so the searched word shows, or null when it
/// already shows at [level]. `('全部', null)` means the word has no level.
({String word, String? level})? databaseSearchElsewhere(
    Map<String, dynamic> image, LexiconPack pack, String query, String? level) {
  if (level == null) return null;
  final hits = databaseSearchHits(image, pack, query);
  if (hits.isEmpty || hits.any((h) => h.$2 == level)) return null;
  return (word: hits.first.$1, level: hits.first.$2);
}

/// CEFR for a database tag: pack lexeme first, then tag metadata from the tagger.
String? databaseTagLevel(Map<String, dynamic> tag, LexiconPack pack) {
  final id = (tag['lexeme_id'] as num?)?.toInt();
  final word = id == null ? null : pack.byId(id);
  final raw =
      (tag['cefr'] as String?) ?? (tag['modelLevel'] as String?) ?? word?.cefr;
  if (raw == null) return null;
  final level = raw.toUpperCase();
  return cefrLevels.contains(level) ? level : null;
}

/// The tag's level is a frequency estimate, not from the CEFR-J / Octanove
/// lists (問題回報 #139 decision: 標「估算」; #132 noodle C1).
bool databaseTagEstimated(Map<String, dynamic> tag, LexiconPack pack) {
  final source = tag['cefr_source'];
  if (source != null) {
    return source == 'estimate' ||
        source == 'frequency_estimate' ||
        source == 'ai_reviewed';
  }
  final id = (tag['lexeme_id'] as num?)?.toInt();
  return id != null && (pack.byId(id)?.cefrEstimated ?? false);
}

/// 「中階（B1）」, or 「進階（C1）・估算」 for a frequency estimate.
String levelText(String level, {bool estimated = false}) =>
    estimated ? '${levelLabel(level)}・估' : levelLabel(level);

/// Approved tags grouped by CEFR (A1→C2), then unleveled.
List<MapEntry<String?, List<Map<String, dynamic>>>> groupedDatabaseImageTags(
    Map<String, dynamic> image, LexiconPack pack) {
  final byLevel = {
    for (final level in cefrLevels) level: <Map<String, dynamic>>[]
  };
  final unknown = <Map<String, dynamic>>[];
  for (final tag in databaseImageTags(image)) {
    final level = databaseTagLevel(tag, pack);
    if (level == null) {
      unknown.add(tag);
    } else {
      byLevel[level]!.add(tag);
    }
  }
  return [
    for (final level in cefrLevels)
      if (byLevel[level]!.isNotEmpty)
        MapEntry<String?, List<Map<String, dynamic>>>(level, byLevel[level]!),
    if (unknown.isNotEmpty)
      MapEntry<String?, List<Map<String, dynamic>>>(null, unknown),
  ];
}

/// A database picture as a photo the pinned view can show.
Photo databasePhoto(Map<String, dynamic> image) {
  final resolved = resolvePackMedia(image['url'] as String);
  final asset = packMediaIsAsset(resolved);
  return Photo(
      id: 'db-${image['id']}',
      title: '',
      takenAt: DateTime(2000),
      createdAt: DateTime(2000),
      assetPath: asset ? resolved : null,
      networkUrl: asset ? null : resolved,
      width: (image['width'] as num?)?.toInt(),
      height: (image['height'] as num?)?.toInt(),
    );
}

/// The vision model's labels on a database picture, as photo pins where it
/// saw them: words in the lexicon first, with their Chinese. With [level],
/// only labels whose approved tag is at that CEFR level (問題回報 #113).
List<PinData> databasePins(Map<String, dynamic> image, LexiconPack pack,
    {int? max, String? level}) {
  final approvedIds = databaseImageTags(image)
      .where((tag) => level == null || databaseTagLevel(tag, pack) == level)
      .map((tag) => (tag['lexeme_id'] as num?)?.toInt())
      .whereType<int>()
      .toSet();
  final labels = [
    for (final l in (image['labels'] as List? ?? []))
      if ((l as Map)['lexeme_id'] is num &&
          approvedIds.contains((l['lexeme_id'] as num).toInt()) &&
          (pack.byId((l['lexeme_id'] as num).toInt())?.full ?? false))
        Map<String, dynamic>.from(l)
  ];
  final pins = <PinData>[];
  for (final l in labels) {
    final point = [
      for (final v in (l['point'] as List? ?? [])) (v as num).toDouble()
    ];
    if (point.length < 2) continue;
    var x = point[0], y = point[1];
    final box = [
      for (final v in (l['box'] as List? ?? [])) (v as num).toDouble()
    ];
    if (box.length == 4 && x == 0.5 && y == 0.5) {
      // The model's "middle of the picture": the middle of its box instead.
      x = (box[0] + box[2]) / 2;
      y = (box[1] + box[3]) / 2;
    }
    final id = (l['lexeme_id'] as num?)?.toInt();
    final entry = id == null ? null : pack.byId(id);
    pins.add(PinData(
        id: '${l['word']}',
        anchor: LabelPoint(x, y),
        word: '${l['word']}',
        zh: entry?.nativeMeaning?.split('、').first ?? '',
        entryType: entry?.entryType ?? 'word',
        linked: entry != null,
        lexemeId: entry?.id));
    if (max != null && pins.length >= max) break;
  }
  return pins;
}

void openDatabaseWord(BuildContext context, int id) =>
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => DatabaseWordScreen(wordId: id)));
