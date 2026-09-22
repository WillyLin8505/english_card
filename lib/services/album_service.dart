import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:hive_flutter/hive_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';
import '../models/models.dart';

class AlbumService {
  static const String _boxName = 'album_entries';
  static const String _imagesDirName = 'album_images';
  static Box<String>? _box;
  static String? _imagesDir;
  static const _uuid = Uuid();

  static Future<void> init() async {
    await Hive.initFlutter();
    _box = await Hive.openBox<String>(_boxName);

    if (!kIsWeb) {
      final appDir = await getApplicationDocumentsDirectory();
      _imagesDir = '${appDir.path}/$_imagesDirName';
      final dir = Directory(_imagesDir!);
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
    }
  }

  static Future<AlbumEntry> saveEntry({
    required Uint8List imageBytes,
    required List<Label> labels,
    String? existingId,
    String? existingImagePath,
  }) async {
    if (_box == null) {
      throw StateError('AlbumService not initialized. Call init() first.');
    }

    final id = existingId ?? _uuid.v4();
    final now = DateTime.now();
    String imagePath;

    if (existingImagePath != null) {
      imagePath = existingImagePath;
    } else if (kIsWeb) {
      imagePath = 'web_image_$id';
      final key = 'image_$id';
      await _box!.put(key, base64Encode(imageBytes));
    } else {
      imagePath = '$_imagesDir/$id.jpg';
      final file = File(imagePath);
      await file.writeAsBytes(imageBytes);
    }

    final entry = AlbumEntry(
      id: id,
      createdAt: now,
      imagePath: imagePath,
      labels: labels,
    );

    await _box!.put(id, jsonEncode(entry.toJson()));
    return entry;
  }

  static Future<void> updateEntry(AlbumEntry entry) async {
    if (_box == null) {
      throw StateError('AlbumService not initialized. Call init() first.');
    }
    await _box!.put(entry.id, jsonEncode(entry.toJson()));
  }

  static Future<List<AlbumEntry>> getAllEntries() async {
    if (_box == null) {
      throw StateError('AlbumService not initialized. Call init() first.');
    }

    final entries = <AlbumEntry>[];
    for (final key in _box!.keys) {
      if (key.toString().startsWith('image_')) continue;
      final json = _box!.get(key);
      if (json != null) {
        try {
          entries.add(AlbumEntry.fromJson(jsonDecode(json)));
        } catch (_) {
          // Skip invalid entries
        }
      }
    }

    entries.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return entries;
  }

  static Future<AlbumEntry?> getEntry(String id) async {
    if (_box == null) {
      throw StateError('AlbumService not initialized. Call init() first.');
    }

    final json = _box!.get(id);
    if (json == null) return null;

    try {
      return AlbumEntry.fromJson(jsonDecode(json));
    } catch (_) {
      return null;
    }
  }

  static Future<void> deleteEntry(String id) async {
    if (_box == null) {
      throw StateError('AlbumService not initialized. Call init() first.');
    }

    final entry = await getEntry(id);
    if (entry != null) {
      if (kIsWeb) {
        await _box!.delete('image_$id');
      } else {
        final file = File(entry.imagePath);
        if (await file.exists()) {
          await file.delete();
        }
      }
    }

    await _box!.delete(id);
  }

  static Future<Uint8List?> getImageBytes(String id) async {
    if (_box == null) return null;

    if (kIsWeb) {
      final base64 = _box!.get('image_$id');
      if (base64 != null) {
        return base64Decode(base64);
      }
    }
    return null;
  }

  static int get entryCount => _box?.length ?? 0;
}
