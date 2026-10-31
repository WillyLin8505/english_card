part of '../screens/database_library_screen.dart';

/// Pictures this entry shows, using the pack's picture_ids (the same rule
/// as the missing-picture count and the fetch queue).
///
/// At most [maxEntryImages] (卡 #854, 問題回報 #1111): the first picture in
/// the catalog stays as the representative one, the rest are picked at random
/// each time the card opens. The catalog keeps every binding.
const maxEntryImages = 5;

List<Map<String, dynamic>> databaseEntryImages(
    List<Map<String, dynamic>> catalog, LexEntry word,
    {math.Random? random}) {
  if (word.pictureIds != null && word.pictureIds!.isEmpty) return const [];
  final ids = (word.pictureIds ?? [word.id]).toSet();
  final all = [
    for (final image in catalog)
      if (databaseImageTags(image)
          .any((tag) => ids.contains((tag['lexeme_id'] as num?)?.toInt())))
        image
  ];
  if (all.length <= maxEntryImages) return all;
  // Seeded per word and minute so a rebuild while the card is open keeps the
  // same photos; opening it again later draws a new set.
  final seed = word.id * 1000003 + DateTime.now().millisecondsSinceEpoch ~/ 60000;
  final rest = all.sublist(1)..shuffle(random ?? math.Random(seed));
  return [all.first, ...rest.take(maxEntryImages - 1)];
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
/// already shows at [level] — its own tags or the ones borrowed from nearby
/// levels (問題回報 #763). `('全部', null)` means the word has no level.
({String word, String? level})? databaseSearchElsewhere(
    Map<String, dynamic> image, LexiconPack pack, String query, String? level) {
  if (level == null) return null;
  final hits = databaseSearchHits(image, pack, query);
  if (hits.isEmpty) return null;
  final shown = {
    for (final tag in databaseLevelTags(image, pack, level))
      (
        pack.byId((tag['lexeme_id'] as num).toInt())?.lemma ?? query.trim(),
        databaseTagLevel(tag, pack)
      )
  };
  if (hits.any(shown.contains)) return null;
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

/// Where a catalog label's pin goes, or null when it has no usable point.
/// The model's "middle of the picture" (0.5, 0.5) becomes the middle of its
/// box. Card #225 round 160: 517 labels on 124 photos sit at (0, 0) — the
/// tagger's "don't know" — and drew a pile of pins in the top-left corner
/// (47 photos had every pin there); without a box they count as no point.
(double, double)? databaseLabelPoint(Map l) {
  // 問題回報 #703 / Windows 卡 #631: a default-centre guess the tagger
  // flagged is no point either.
  if (labelPointUngrounded(l)) return null;
  final point = [
    for (final v in (l['point'] as List? ?? [])) (v as num).toDouble()
  ];
  if (point.length < 2) return null;
  final box = [
    for (final v in (l['box'] as List? ?? [])) (v as num).toDouble()
  ];
  final x = point[0], y = point[1];
  final centre = (x == 0.5 && y == 0.5) || (x == 0 && y == 0);
  if (centre && box.length == 4) {
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2);
  }
  if (x == 0 && y == 0) return null;
  return (x, y);
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

/// The tags a picture lists at [level] (問題回報 #763, owner chose A): its own
/// tags at that level, and when they are fewer than [WordSelector.maxWords],
/// tags from the nearest levels — easier first, then harder, the same order
/// as 照片詳情 (WordSelector.nearestLevelOrder). A level with five or more
/// tags of its own keeps them all. Unleveled tags are not borrowed; they
/// show under 全部.
List<Map<String, dynamic>> databaseLevelTags(
    Map<String, dynamic> image, LexiconPack pack, String level) {
  final target = levelIndex(level);
  final own = <Map<String, dynamic>>[];
  final nearby = <(int, int, Map<String, dynamic>)>[];
  for (final tag in databaseImageTags(image)) {
    final l = databaseTagLevel(tag, pack);
    if (l == null) continue;
    if (l == level) {
      own.add(tag);
    } else {
      nearby.add((
        WordSelector.nearestLevelOrder(levelIndex(l), target),
        nearby.length,
        tag
      ));
    }
  }
  if (own.length >= WordSelector.maxWords) return own;
  nearby.sort(
      (a, b) => a.$1 != b.$1 ? a.$1.compareTo(b.$1) : a.$2.compareTo(b.$2));
  return [
    ...own,
    for (final t in nearby.take(WordSelector.maxWords - own.length)) t.$3
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
    // 問題回報 #859: the same downscaled copy the review asks for, so
    // both share one download and one cached file.
    networkUrl: asset ? null : sizedServerImage(resolved),
    width: (image['width'] as num?)?.toInt(),
    height: (image['height'] as num?)?.toInt(),
  );
}

/// The vision model's labels on a database picture, as photo pins where it
/// saw them: words in the lexicon first, with their Chinese. With [level],
/// only labels whose approved tag is listed at that level (問題回報 #113):
/// with [borrow] that includes the words filled in from nearby levels, so
/// the pins match the list (問題回報 #763); without it, only the level's own.
List<PinData> databasePins(Map<String, dynamic> image, LexiconPack pack,
    {int? max, String? level, bool borrow = true}) {
  final tags = level == null
      ? databaseImageTags(image)
      : borrow
          ? databaseLevelTags(image, pack, level)
          : databaseImageTags(image)
              .where((tag) => databaseTagLevel(tag, pack) == level);
  final approvedIds = tags
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
    final point = databaseLabelPoint(l);
    if (point == null) continue;
    final x = point.$1, y = point.$2;
    final id = (l['lexeme_id'] as num?)?.toInt();
    final entry = id == null ? null : pack.byId(id);
    // Card #496 round 7: 26 French photos label one spelling twice (vert
    // noun + vert adj, rond…); keyed by the word alone the pins collide
    // (Duplicate keys) and a tap on one opens the other, so the lexeme id
    // tells them apart.
    pins.add(PinData(
        id: id == null ? '${l['word']}' : '${l['word']}#$id',
        anchor: LabelPoint(x, y),
        word: '${l['word']}',
        zh: _pinMeaning(entry, l, tags)?.split('、').first ?? '',
        entryType: entry?.entryType ?? 'word',
        linked: entry != null,
        lexemeId: entry?.id));
    if (max != null && pins.length >= max) break;
  }
  return pins;
}

/// The meaning a pin shows (圖 43: open 可通行 instead of 打開的): the
/// label's sense, else the sense of the same word's approved tag, else
/// the word's first meaning.
String? _pinMeaning(
    LexEntry? entry, Map<String, dynamic> label, Iterable<Map> tags) {
  if (entry == null) return null;
  final id = label['sense_id'] ??
      tags
          .where((t) =>
              (t['lexeme_id'] as num?)?.toInt() == entry.id &&
              t['sense_id'] != null)
          .firstOrNull?['sense_id'];
  final sense =
      id == null ? null : entry.senses.where((s) => s.id == id).firstOrNull;
  final native = sense?.native?.trim();
  return native == null || native.isEmpty ? entry.nativeMeaning : native;
}

void openDatabaseWord(BuildContext context, int id) =>
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => DatabaseWordScreen(wordId: id)));
