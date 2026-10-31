import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:path_provider/path_provider.dart';

import '../models/photo.dart';

/// Keeps the pixels of photos the user adds. Spec: "原圖留裝置" — the
/// original stays on this device and Photo records only reference it.
///
/// On phones and desktop the image is written to the app's documents
/// folder (the picker's own copy is a temporary cache file). On the web
/// there is no file system, so the bytes go into a local Hive box.
class PhotoStore {
  static const _boxName = 'wd_photo_bytes';

  final LazyBox<Uint8List>? _box;
  final Directory? _dir;

  PhotoStore._(this._box, this._dir);

  @visibleForTesting
  PhotoStore.fromLazyBox(LazyBox<Uint8List> box) : this._(box, null);

  /// A store that keeps bytes in memory only — tests.
  PhotoStore.inMemory()
      : _box = null,
        _dir = null;

  /// A store over [dir] — tests of the on-disk behaviour.
  @visibleForTesting
  PhotoStore.inDirectory(Directory dir) : this._(null, dir);

  final _memory = <String, Uint8List>{};

  static Future<PhotoStore> open() async {
    if (kIsWeb) {
      // Keep the existing box/key format; only load keys at startup.
      return PhotoStore._(await Hive.openLazyBox<Uint8List>(_boxName), null);
    }
    final docs = await getApplicationDocumentsDirectory();
    final dir =
        Directory('${docs.path}${Platform.pathSeparator}english_card_photos');
    await dir.create(recursive: true);
    photosDirectory = dir.path;
    return PhotoStore._(null, dir);
  }

  /// This install's photo folder. iOS gives the app a new container path on
  /// every install and update, so a saved [Photo.filePath] can name a folder
  /// that is gone while the picture is still here (問題回報 #614).
  @visibleForTesting
  static String? photosDirectory;

  static final _resolved = <String, String>{};

  static String _fileName(String path) => path.split(RegExp(r'[/\\]')).last;

  /// Where [path] (a saved [Photo.filePath]) is on this install: the path
  /// itself when it exists, else the same file name in [photosDirectory].
  static String localPath(String path) {
    if (kIsWeb) return path;
    final known = _resolved[path];
    if (known != null) return known;
    var found = path;
    try {
      final dir = photosDirectory;
      if (!File(path).existsSync() && dir != null) {
        final name = _fileName(path);
        final here = '$dir${Platform.pathSeparator}$name';
        if (name.isNotEmpty && File(here).existsSync()) found = here;
      }
    } on FileSystemException {
      // Keep [path]; lostOriginal reports it.
    }
    if (found != path || File(found).existsSync()) _resolved[path] = found;
    return found;
  }

  /// Saves [bytes] for [photoId]. Returns where it went: a file path, or
  /// a key for [storedBytes].
  Future<({String? filePath, String? storedKey})> save(
    String photoId,
    Uint8List bytes,
  ) async {
    final dir = _dir;
    if (dir != null) {
      final file = File('${dir.path}${Platform.pathSeparator}$photoId.jpg');
      await file.writeAsBytes(bytes, flush: true);
      return (filePath: file.path, storedKey: null);
    }
    final box = _box;
    if (box != null) {
      await box.put(photoId, bytes);
    } else {
      _memory[photoId] = bytes;
    }
    return (filePath: null, storedKey: photoId);
  }

  Future<Uint8List?> storedBytes(String key) async =>
      _box == null ? _memory[key] : await _box.get(key);

  /// Deletes the app's own copy of a photo (問題回報 #1179). Only this folder
  /// is touched, by file name: spec section 7 keeps the original in the
  /// phone's system album.
  Future<void> remove({String? filePath, String? storedKey}) async {
    final dir = _dir;
    if (dir != null) {
      if (filePath == null) return;
      _resolved.remove(filePath);
      final name = _fileName(filePath);
      if (name.isEmpty) return;
      try {
        await File('${dir.path}${Platform.pathSeparator}$name').delete();
      } on FileSystemException catch (e) {
        debugPrint('Photo file not deleted: $e');
      }
      return;
    }
    if (storedKey == null) return;
    final box = _box;
    if (box != null) {
      await box.delete(storedKey);
    } else {
      _memory.remove(storedKey);
    }
  }

  /// After a restore (問題回報 #1180): deletes every picture in the app's
  /// folder except those of [keepIds] (the photos the backup brought back);
  /// the records that pointed at the others were just replaced. Returns how
  /// many files went.
  Future<int> removeAllExcept(Set<String> keepIds) async {
    final dir = _dir;
    if (dir == null) return 0;
    var removed = 0;
    try {
      for (final file in await dir.list().toList()) {
        if (file is! File || !file.path.endsWith('.jpg')) continue;
        final name = _fileName(file.path);
        if (keepIds.contains(name.substring(0, name.length - 4))) continue;
        await file.delete();
        removed++;
      }
    } catch (e) {
      debugPrint('Photo cleanup after restore failed: $e');
    }
    return removed;
  }

  static const _sweptMark = '.orphans_swept';

  /// Once per install: deletes the pictures of photos removed before
  /// [remove] existed. [savedPaths] gives every language's [Photo.filePath];
  /// if it fails or finds no photo at all, nothing is deleted and the next
  /// start tries again. A file from the last day stays: its record may still
  /// be on its way. Returns how many files went.
  Future<int> sweepOrphansOnce(
    Future<Iterable<String?>> Function() savedPaths, {
    DateTime? now,
  }) async {
    final dir = _dir;
    if (dir == null) return 0;
    try {
      final mark = File('${dir.path}${Platform.pathSeparator}$_sweptMark');
      if (await mark.exists()) return 0;
      final keep = {
        for (final path in await savedPaths())
          if (path != null) _fileName(path)
      };
      if (keep.isEmpty) return 0;
      final cutoff = (now ?? DateTime.now()).subtract(const Duration(days: 1));
      var removed = 0;
      for (final file in await dir.list().toList()) {
        if (file is! File || !file.path.endsWith('.jpg')) continue;
        if (keep.contains(_fileName(file.path))) continue;
        if ((await file.stat()).modified.isAfter(cutoff)) continue;
        await file.delete();
        removed++;
      }
      await mark.writeAsString('');
      return removed;
    } catch (e) {
      debugPrint('Photo sweep failed: $e');
      return 0;
    }
  }

  /// Whether [photo]'s picture can be shown now. A photo whose original
  /// file is gone (deleted, or no permission to read it) cannot: callers
  /// show another picture of the word instead of a broken one (問題回報 #279).
  static bool canShow(Photo photo) => photo.hasImage && !lostOriginal(photo);

  /// Whether [photo] points at an original file that is gone. Photos that
  /// never had a picture are not "lost": lists keep drawing their
  /// placeholder, and only lost ones are skipped (問題回報 #283).
  static bool lostOriginal(Photo photo) {
    final path = photo.filePath;
    if (path == null || kIsWeb) return false;
    try {
      return !File(localPath(path)).existsSync();
    } on FileSystemException {
      return true;
    }
  }
}
