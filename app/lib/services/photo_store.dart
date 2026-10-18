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
    return PhotoStore._(null, dir);
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

  /// Whether [photo]'s picture can be shown now. A photo whose original
  /// file is gone (deleted, or no permission to read it) cannot: callers
  /// show another picture of the word instead of a broken one (問題回報 #279).
  static bool canShow(Photo photo) =>
      photo.hasImage && !lostOriginal(photo);

  /// Whether [photo] points at an original file that is gone. Photos that
  /// never had a picture are not "lost": lists keep drawing their
  /// placeholder, and only lost ones are skipped (問題回報 #283).
  static bool lostOriginal(Photo photo) {
    final path = photo.filePath;
    if (path == null || kIsWeb) return false;
    try {
      return !File(path).existsSync();
    } on FileSystemException {
      return true;
    }
  }
}
