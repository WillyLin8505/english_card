import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:path_provider/path_provider.dart';

/// Keeps the pixels of photos the user adds. Spec: "原圖留裝置" — the
/// original stays on this device and Photo records only reference it.
///
/// On phones and desktop the image is written to the app's documents
/// folder (the picker's own copy is a temporary cache file). On the web
/// there is no file system, so the bytes go into a local Hive box.
class PhotoStore {
  static const _boxName = 'wd_photo_bytes';

  final Box<Uint8List>? _box;
  final Directory? _dir;

  PhotoStore._(this._box, this._dir);

  /// A store that keeps bytes in memory only — tests.
  PhotoStore.inMemory()
      : _box = null,
        _dir = null;

  final _memory = <String, Uint8List>{};

  static Future<PhotoStore> open() async {
    if (kIsWeb) {
      return PhotoStore._(await Hive.openBox<Uint8List>(_boxName), null);
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

  Uint8List? storedBytes(String key) => _box?.get(key) ?? _memory[key];
}
