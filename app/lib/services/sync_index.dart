import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:hive/hive.dart';

/// What sync knows about one record of a [SyncBoxes].
class SyncMark {
  /// Photo bytes: not sent yet / on the server / to fetch / this device has
  /// none to send.
  static const blobToSend = 0, blobSent = 1, blobToFetch = 2, blobNone = 3;

  final int stamp;
  final String device;
  final bool deleted;

  /// Changed here and not uploaded yet.
  final bool pending;

  /// The record's name on every device (see [SyncBoxes.wireOf]).
  final String wire;

  /// Review logs: the record's key in the logs box.
  final int? logKey;
  final int blob;

  /// Settings: the value last seen.
  final String? value;

  const SyncMark({
    required this.stamp,
    required this.wire,
    this.device = '',
    this.deleted = false,
    this.pending = false,
    this.logKey,
    this.blob = blobToSend,
    this.value,
  });

  SyncMark copyWith({bool? pending, int? blob}) => SyncMark(
        stamp: stamp,
        wire: wire,
        device: device,
        deleted: deleted,
        pending: pending ?? this.pending,
        logKey: logKey,
        blob: blob ?? this.blob,
        value: value,
      );

  /// Whether a record stamped ([stamp], [device]) replaces this one.
  bool olderThan(int stamp, String device) =>
      this.stamp < stamp ||
      (this.stamp == stamp && this.device.compareTo(device) < 0);

  factory SyncMark.decode(String raw) {
    final j = jsonDecode(raw) as Map<String, dynamic>;
    return SyncMark(
      stamp: j['t'] as int,
      wire: j['w'] as String,
      device: j['v'] as String? ?? '',
      deleted: j['d'] == 1,
      pending: j['p'] == 1,
      logKey: j['i'] as int?,
      blob: j['b'] as int? ?? blobToSend,
      value: j['x'] as String?,
    );
  }

  String encode() => jsonEncode({
        't': stamp,
        'w': wire,
        if (device.isNotEmpty) 'v': device,
        if (deleted) 'd': 1,
        if (pending) 'p': 1,
        if (logKey != null) 'i': logKey,
        if (blob != blobToSend) 'b': blob,
        if (value != null) 'x': value,
      });
}

/// Stamps for 「每筆更新時間」 (card #912): milliseconds that never repeat on
/// this device and never fall behind a stamp seen from another device, so an
/// edit made after a sync wins even when this device's clock runs slow.
class SyncClock {
  static int _last = 0;

  static int next([int? now]) {
    final t = now ?? DateTime.now().millisecondsSinceEpoch;
    return _last = t > _last ? t : _last + 1;
  }

  static void observe(int stamp) {
    if (stamp > _last) _last = stamp;
  }
}

/// A language's word-database boxes and the sync marks of their records
/// (card #912). Every write of [HiveWordDatabaseStore] goes through here, so
/// a change made offline keeps the time it was made.
///
/// Ids differ between devices (`word-<microseconds>`), but a word has one
/// entry and one card per device: entries and cards are named by the word
/// across devices, so two devices that both saved "apple" share one record and
/// keep their review history on one card.
class SyncBoxes {
  /// Called after a local change; [CloudSync] schedules an upload.
  static void Function()? onLocalChange;

  static const entries = 'entries',
      photos = 'photos',
      albums = 'albums',
      occurrences = 'occurrences',
      cards = 'cards',
      logs = 'logs',
      meta = 'meta',
      decks = 'decks';

  /// Upload order: what a record refers to goes first.
  static const collections = [
    albums,
    entries,
    photos,
    occurrences,
    cards,
    logs,
    meta,
    decks,
  ];

  static const metaKeys = ['template', 'profile', 'fsrsOptimization'];

  final Box<String> entriesBox,
      photosBox,
      albumsBox,
      occurrencesBox,
      cardsBox,
      logsBox,
      metaBox,
      index;

  SyncBoxes({
    required this.entriesBox,
    required this.photosBox,
    required this.albumsBox,
    required this.occurrencesBox,
    required this.cardsBox,
    required this.logsBox,
    required this.metaBox,
    required this.index,
  });

  Box<String>? boxOf(String collection) => switch (collection) {
        entries => entriesBox,
        photos => photosBox,
        albums => albumsBox,
        occurrences => occurrencesBox,
        cards => cardsBox,
        logs => logsBox,
        meta => metaBox,
        _ => null,
      };

  static const _logsIndexedKey = 'logsIndexed',
      _profileBaseKey = 'profileBase';

  static String _key(String collection, String id) => '$collection/$id';

  /// A log's id in the index. Hive keys must be ASCII and short, and a log's
  /// wire name holds the word (école, 蘋果).
  static String logId(String wire) => sha1.convert(utf8.encode(wire)).toString();

  SyncMark? mark(String collection, String id) {
    final raw = index.get(_key(collection, id));
    return raw == null ? null : SyncMark.decode(raw);
  }

  Future<void> setMark(String collection, String id, SyncMark mark) =>
      index.put(_key(collection, id), mark.encode());

  Future<void> forget(String collection, String id) =>
      index.delete(_key(collection, id));

  /// (id, mark) of every record of [collection] this index knows.
  Iterable<(String, SyncMark)> marks(String collection) sync* {
    final prefix = '$collection/';
    for (final k in index.keys) {
      final key = '$k';
      if (key.startsWith(prefix)) {
        yield (key.substring(prefix.length), SyncMark.decode(index.get(k)!));
      }
    }
  }

  /// The word of an entry id; null when the entry is gone.
  String? wordOf(String entryId) {
    final raw = entriesBox.get(entryId);
    return raw == null ? mark(entries, entryId)?.wire : _decode(raw)['word'] as String?;
  }

  static Map<String, dynamic> _decode(String raw) =>
      jsonDecode(raw) as Map<String, dynamic>;

  /// The word of a card id; null for a card of an unknown word.
  String? wordOfCard(String cardId) {
    final raw = cardsBox.get(cardId);
    if (raw != null) return wordOf(_decode(raw)['wordEntryId'] as String);
    final wire = mark(cards, cardId)?.wire;
    return wire == null || wire.startsWith('#') ? null : wire;
  }

  /// A record's name on every device.
  String wireOf(String collection, String id, String raw) {
    switch (collection) {
      case entries:
        return _decode(raw)['word'] as String;
      case cards:
        return wordOf(_decode(raw)['wordEntryId'] as String) ??
            mark(cards, id)?.wire ??
            '#$id';
      case logs:
        final j = _decode(raw);
        final card = j['cardId'] as String;
        return '${wordOfCard(card) ?? '#$card'}|${j['reviewedAt']}|${j['rating']}';
      default:
        return id;
    }
  }

  /// [raw] as it travels: pictures stay where they are on each device, so
  /// a new install or a photo moved between folders is not a change.
  static String comparable(String collection, String raw) {
    if (collection != photos) return raw;
    final j = _decode(raw)
      ..remove('filePath')
      ..remove('storedKey');
    return jsonEncode(j);
  }

  Future<void> touch(String collection, String id, String wire,
      {bool deleted = false}) async {
    final old = mark(collection, id);
    await setMark(
        collection,
        id,
        SyncMark(
          stamp: SyncClock.next(),
          wire: wire,
          deleted: deleted,
          pending: true,
          logKey: old?.logKey,
          blob: old?.blob ?? SyncMark.blobToSend,
        ));
    onLocalChange?.call();
  }

  /// Writes [raw] for [id]; stamps it only when it really changed, because
  /// the enrichers and start-up refreshes rewrite records with the same text.
  Future<void> put(String collection, String id, String raw) async {
    final box = boxOf(collection)!;
    final old = box.get(id);
    await box.put(id, raw);
    if (old != null &&
        comparable(collection, old) == comparable(collection, raw) &&
        mark(collection, id) != null) {
      return;
    }
    await touch(collection, id, wireOf(collection, id, raw));
  }

  Future<void> delete(String collection, String id) async {
    final box = boxOf(collection)!;
    final old = box.get(id);
    final known = mark(collection, id);
    if (old == null && known == null) return;
    final wire = known?.wire ?? wireOf(collection, id, old!);
    await box.delete(id);
    await touch(collection, id, wire, deleted: true);
  }

  Future<void> addLog(String raw) async {
    final key = await logsBox.add(raw);
    final wire = wireOf(logs, '', raw);
    await setMark(
        logs,
        logId(wire),
        SyncMark(
            stamp: SyncClock.next(), wire: wire, pending: true, logKey: key));
    onLocalChange?.call();
  }

  /// Gives records written before sync existed (or put back by 從備份還原) a
  /// mark. Their stamp is their own date, so a first merge of two devices
  /// keeps the newer version of a word.
  Future<void> indexExisting(String device) async {
    for (final collection in [albums, entries, photos, occurrences, cards]) {
      final box = boxOf(collection)!;
      for (final k in box.keys) {
        final id = '$k';
        if (mark(collection, id) != null) continue;
        final raw = box.get(k)!;
        await setMark(
            collection,
            id,
            SyncMark(
                stamp: _ownDate(raw),
                wire: wireOf(collection, id, raw),
                device: device,
                pending: true));
      }
    }
    for (final id in metaKeys) {
      final raw = metaBox.get(id);
      if (raw == null || mark(meta, id) != null) continue;
      await setMark(meta, id,
          SyncMark(stamp: _ownDate(raw), wire: id, device: device, pending: true));
    }
    if (index.get(_logsIndexedKey) == '${logsBox.length}') return;
    for (final k in logsBox.keys) {
      final raw = logsBox.get(k)!;
      final wire = wireOf(logs, '', raw);
      if (mark(logs, logId(wire)) != null) continue;
      await setMark(
          logs,
          logId(wire),
          SyncMark(
              stamp: _ownDate(raw),
              wire: wire,
              device: device,
              pending: true,
              logKey: k as int));
    }
    await index.put(_logsIndexedKey, '${logsBox.length}');
  }

  static int _ownDate(String raw) {
    try {
      final j = jsonDecode(raw);
      if (j is Map) {
        for (final f in const ['updatedAt', 'reviewedAt', 'createdAt', 'takenAt']) {
          final at = DateTime.tryParse('${j[f]}');
          if (at != null) return at.millisecondsSinceEpoch;
        }
      }
    } on FormatException {
      // Not JSON: older than anything stamped.
    }
    return 1;
  }

  /// The profile both sides last agreed on: tells a word removed from a word
  /// the other side never had.
  String? get profileBase => index.get(_profileBaseKey);

  Future<void> setProfileBase(String raw) => index.put(_profileBaseKey, raw);

  int get pendingCount {
    var n = 0;
    for (final k in index.keys) {
      if (k == _logsIndexedKey || k == _profileBaseKey) continue;
      if (SyncMark.decode(index.get(k)!).pending) n++;
    }
    return n;
  }
}
