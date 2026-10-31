import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import '../models/photo.dart';
import 'app_settings.dart';
import 'photo_store.dart';
import 'word_database_store.dart';

/// Thrown when a file is not a backup this app version can restore. The
/// message is shown to the learner as is.
class BackupException implements Exception {
  final String message;
  const BackupException(this.message);

  @override
  String toString() => message;
}

/// What a backup holds, for the message after export / restore.
class BackupSummary {
  final int words;
  final int photos;
  final int reviews;
  final int photoBytes;
  const BackupSummary(
      {this.words = 0, this.photos = 0, this.reviews = 0, this.photoBytes = 0});
}

/// 備份與還原 (問題回報 #278): every learning language's words, photos,
/// albums, cards, review history and profile, the photos' pixels and
/// 設定, in one file.
///
/// File layout (version 1):
/// - line 1: `ENGLISH-CARD-BACKUP 1`
/// - line 2: the manifest, one line of JSON
/// - per photo: one line of JSON (`{"key":"en/<photoId>","size":N}`)
///   followed by its N raw bytes.
///
/// Photos are raw bytes, not base64, and are read and written one at a
/// time, so a large album never has to sit in memory as text.
///
/// Boxes are copied as the JSON strings the store keeps, so an older
/// app's backup is restored as that version stored it and
/// [HiveWordDatabaseStore.open] migrates it (schema 2 → 3). A backup
/// whose schema or file version is newer than this app is refused.
///
/// The tagging server address and API key are not backed up: they belong
/// to this device, and the key is a secret that should not travel inside
/// a shared file.
class AppBackup {
  static const magic = 'ENGLISH-CARD-BACKUP';
  static const version = 1;
  static const fileExtension = 'ecbackup';

  static const _boxSuffixes = [
    'entries',
    'photos',
    'albums',
    'occurrences',
    'cards',
    'review_logs',
    'meta',
  ];

  /// Writes a backup through [write], one chunk at a time.
  /// [readFile] loads a photo saved as a file (defaults to dart:io).
  static Future<BackupSummary> write({
    required AppSettings settings,
    required PhotoStore photoStore,
    required Future<void> Function(List<int> bytes) write,
    Future<Uint8List?> Function(String path)? readFile,
    DateTime? now,
  }) async {
    readFile ??= _readFile;
    final languages = <String, Map<String, Object>>{};
    final photos = <({String key, Map<String, dynamic> json})>[];
    var words = 0, reviews = 0;
    for (final language in supportedLanguages.keys) {
      final boxes = await _open(language);
      if (boxes.values.every((b) => b.isEmpty)) continue;
      languages[language] = {
        for (final e in boxes.entries)
          e.key: e.key == 'review_logs'
              ? e.value.values.toList()
              : {for (final k in e.value.keys) '$k': e.value.get(k)},
      };
      words += boxes['entries']!.length;
      reviews += boxes['review_logs']!.length;
      for (final raw in boxes['photos']!.values) {
        final json = jsonDecode(raw) as Map<String, dynamic>;
        photos.add((key: '$language/${json['id']}', json: json));
      }
    }

    final manifest = {
      'format': 'english_card_backup',
      'version': version,
      'createdAt': (now ?? DateTime.now()).toUtc().toIso8601String(),
      'schema': HiveWordDatabaseStore.schemaVersion,
      'settings': settingsOf(settings),
      'languages': languages,
    };
    await write(utf8.encode('$magic $version\n${jsonEncode(manifest)}\n'));
    var totalBytes = 0, photoCount = 0;
    for (final p in photos) {
      final bytes = await photoBytes(p.json, photoStore, readFile: readFile);
      if (bytes == null) continue;
      await write(
          utf8.encode('${jsonEncode({'key': p.key, 'size': bytes.length})}\n'));
      await write(bytes);
      totalBytes += bytes.length;
      photoCount++;
    }
    // End marker: lets restore tell a complete file from a cut-off one.
    await write(utf8.encode('${jsonEncode({'end': photoCount})}\n'));
    return BackupSummary(
        words: words,
        photos: photoCount,
        reviews: reviews,
        photoBytes: totalBytes);
  }

  /// The pixels of the photo record [p]. Photos whose file is gone give null
  /// and are left out (their record still restores, showing no picture).
  static Future<Uint8List?> photoBytes(
    Map<String, dynamic> p,
    PhotoStore photoStore, {
    Future<Uint8List?> Function(String path)? readFile,
  }) async {
    final path = p['filePath'] as String?;
    final key = p['storedKey'] as String?;
    if (path != null && !kIsWeb) {
      return (readFile ?? _readFile)(PhotoStore.localPath(path));
    }
    if (key != null) return photoStore.storedBytes(key);
    return null;
  }

  /// A backup in memory — the web, and tests.
  static Future<(Uint8List, BackupSummary)> toBytes({
    required AppSettings settings,
    required PhotoStore photoStore,
    Future<Uint8List?> Function(String path)? readFile,
    DateTime? now,
  }) async {
    final out = BytesBuilder(copy: false);
    final summary = await write(
      settings: settings,
      photoStore: photoStore,
      write: (b) async => out.add(b),
      readFile: readFile,
      now: now,
    );
    return (out.takeBytes(), summary);
  }

  /// Replaces all of the learner's data with the backup read from
  /// [input]. Nothing is changed until the whole file has been checked
  /// and its photos saved, so a damaged or newer file leaves the current
  /// data as it was. The caller reopens the word database afterwards.
  static Future<BackupSummary> restore(
    Stream<List<int>> input, {
    required AppSettings settings,
    required PhotoStore photoStore,
  }) async {
    final reader = _ByteReader(input);
    try {
      final first = await reader.readLine(maxLength: 64);
      final parts = first?.split(' ');
      if (parts == null || parts.length != 2 || parts[0] != magic) {
        throw const BackupException('這不是拍照學單字的備份檔');
      }
      final fileVersion = int.tryParse(parts[1]) ?? 0;
      if (fileVersion < 1) throw const BackupException('這不是拍照學單字的備份檔');
      if (fileVersion > version) {
        throw const BackupException('這個備份來自較新版本的 App，請先更新 App 再還原');
      }
      final line = await reader.readLine();
      final manifest = line == null ? null : _tryDecode(line);
      if (manifest == null || manifest['format'] != 'english_card_backup') {
        throw const BackupException('備份檔已損壞，無法讀取');
      }
      final languages = (manifest['languages'] as Map?) ?? const {};
      for (final data in languages.values) {
        final meta = (data as Map)['meta'] as Map?;
        final schema = int.tryParse('${meta?['schema']}') ?? 0;
        if (schema > HiveWordDatabaseStore.schemaVersion) {
          throw const BackupException('這個備份來自較新版本的 App，請先更新 App 再還原');
        }
      }

      // Photos first: saved under their own ids, so the current data is
      // untouched if the file turns out to be cut off.
      final saved = <String, ({String? filePath, String? storedKey})>{};
      var photoBytes = 0;
      while (true) {
        final header = await reader.readLine();
        final h = header == null ? null : _tryDecode(header);
        if (h == null) throw const BackupException('備份檔不完整，可能沒有存完');
        if (h.containsKey('end')) break;
        final key = h['key'] as String;
        final size = h['size'] as int;
        final bytes = await reader.read(size);
        if (bytes == null) throw const BackupException('備份檔不完整，可能沒有存完');
        saved[key] = await photoStore.save(key.split('/').last, bytes);
        photoBytes += size;
      }

      var words = 0, reviews = 0, photos = 0;
      for (final language in supportedLanguages.keys) {
        final boxes = await _open(language);
        for (final box in boxes.values) {
          await box.clear();
        }
        final data = languages[language] as Map?;
        if (data == null) continue;
        for (final suffix in _boxSuffixes) {
          final box = boxes[suffix]!;
          final content = data[suffix];
          if (suffix == 'review_logs') {
            final logs = [for (final v in (content as List?) ?? const []) '$v'];
            await box.addAll(logs);
            reviews += logs.length;
            continue;
          }
          final values = {
            for (final e in ((content as Map?) ?? const {}).entries)
              '${e.key}': suffix == 'photos'
                  ? _relocate('${e.value}', language, saved)
                  : '${e.value}',
          };
          await box.putAll(values);
          if (suffix == 'entries') words += values.length;
          if (suffix == 'photos') photos += values.length;
        }
      }
      // Pictures no restored record points at (the old records are gone).
      await photoStore.removeAllExcept({
        for (final k in saved.keys) k.split('/').last,
      });
      applySettings(settings, manifest['settings']);
      // The sync marks described what was just replaced.
      for (final language in supportedLanguages.keys) {
        final p = HiveWordDatabaseStore.prefixFor(language);
        await (await Hive.openBox<String>('${p}sync')).clear();
      }
      // Read the account again from the start, as a new device: it holds what
      // was changed since this backup, and it skips this device's own uploads.
      await (await Hive.openBox<String>('sync_state'))
          .deleteAll(const ['cursor', 'device']);
      return BackupSummary(
          words: words,
          photos: photos,
          reviews: reviews,
          photoBytes: photoBytes);
    } finally {
      await reader.cancel();
    }
  }

  /// Points a restored photo at where its bytes were saved on this
  /// device: the old path belonged to the other install (an iPhone's app
  /// folder changes on every reinstall).
  static String _relocate(String raw, String language,
      Map<String, ({String? filePath, String? storedKey})> saved) {
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final where = saved['$language/${json['id']}'];
    if (where == null) {
      // No pixels in the backup: drop the dead reference.
      if (json['filePath'] != null || json['storedKey'] != null) {
        json['filePath'] = null;
        json['storedKey'] = null;
      } else {
        return raw;
      }
    } else {
      json['filePath'] = where.filePath;
      json['storedKey'] = where.storedKey;
    }
    return jsonEncode(json);
  }

  static Map<String, Object> settingsOf(AppSettings s) => {
        'learningLanguage': s.learningLanguage,
        'nativeLanguage': s.nativeLanguage,
        'englishAccent': s.englishAccent,
        'cardStyle': s.cardStyle.name,
        'desiredRetention': s.desiredRetention,
        'shareUsageStats': s.shareUsageStats,
        'dailyNewLimit': s.dailyNewLimit,
        'dailyReviewLimit': s.dailyReviewLimit,
        'showPhotoLabels': s.showPhotoLabels,
        'learningGoals': s.learningGoals,
        'interests': s.interests,
        'reviewScope': s.reviewScope,
        'scanMode': s.scanMode.name,
      };

  static void applySettings(AppSettings s, Object? raw) {
    if (raw is! Map) return;
    if (raw['learningLanguage'] case final String v
        when learningLanguageAvailable(v)) {
      s.learningLanguage = v;
    }
    if (raw['nativeLanguage'] case final String v
        when nativeLanguageAvailable(v)) {
      s.nativeLanguage = v;
    }
    if (raw['englishAccent'] case final String v) s.englishAccent = v;
    if (raw['cardStyle'] case final String v) s.cardStyle = CardStyle.parse(v);
    if (raw['desiredRetention'] case final num v) {
      s.desiredRetention = v.toDouble();
    }
    if (raw['shareUsageStats'] case final bool v) s.shareUsageStats = v;
    if (raw['dailyNewLimit'] case final num v) s.dailyNewLimit = v.toInt();
    if (raw['dailyReviewLimit'] case final num v) {
      s.dailyReviewLimit = v.toInt();
    }
    if (raw['showPhotoLabels'] case final bool v) s.showPhotoLabels = v;
    if (raw['learningGoals'] case final List v) {
      s.learningGoals = [for (final e in v) '$e'];
    }
    if (raw['interests'] case final List v) {
      s.interests = [for (final e in v) '$e'];
    }
    if (raw['reviewScope'] case final String v) s.reviewScope = v;
    if (raw['scanMode'] case final String v
        when PhotoScanMode.values.asNameMap().containsKey(v)) {
      s.scanMode = PhotoScanMode.values.asNameMap()[v]!;
    }
  }

  static Future<Map<String, Box<String>>> _open(String language) async {
    final p = HiveWordDatabaseStore.prefixFor(language);
    return {
      for (final s in _boxSuffixes) s: await Hive.openBox<String>('$p$s'),
    };
  }

  static Map<String, dynamic>? _tryDecode(String line) {
    try {
      final v = jsonDecode(line);
      return v is Map<String, dynamic> ? v : null;
    } on FormatException {
      return null;
    }
  }

  static Future<Uint8List?> _readFile(String path) async {
    final file = File(path);
    return await file.exists() ? file.readAsBytes() : null;
  }
}

/// Reads lines and fixed-size blocks from a byte stream, holding only
/// what has not been consumed yet. Each incoming chunk is copied once.
class _ByteReader {
  final StreamIterator<List<int>> _it;
  List<int> _pending = const [];

  _ByteReader(Stream<List<int>> input) : _it = StreamIterator(input);

  Future<List<int>?> _next() async {
    if (_pending.isNotEmpty) {
      final p = _pending;
      _pending = const [];
      return p;
    }
    return await _it.moveNext() ? _it.current : null;
  }

  /// The next line without its newline; null at the end of the stream, or
  /// when no newline comes within [maxLength] bytes.
  Future<String?> readLine({int? maxLength}) async {
    final out = BytesBuilder(copy: true);
    while (true) {
      final chunk = await _next();
      if (chunk == null) return null;
      final i = chunk.indexOf(10);
      if (i >= 0) {
        out.add(chunk.sublist(0, i));
        _pending = chunk.sublist(i + 1);
        return utf8.decode(out.takeBytes(), allowMalformed: true);
      }
      out.add(chunk);
      if (maxLength != null && out.length > maxLength) return null;
    }
  }

  /// Exactly [n] bytes; null if the stream ends first.
  Future<Uint8List?> read(int n) async {
    final out = BytesBuilder(copy: true);
    while (out.length < n) {
      final chunk = await _next();
      if (chunk == null) return null;
      final need = n - out.length;
      if (chunk.length <= need) {
        out.add(chunk);
      } else {
        out.add(chunk.sublist(0, need));
        _pending = chunk.sublist(need);
      }
    }
    return out.takeBytes();
  }

  Future<void> cancel() => _it.cancel();
}
