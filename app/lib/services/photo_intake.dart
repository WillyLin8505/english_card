import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import '../models/photo.dart';
import 'photo_store.dart';
import 'tagging_service.dart';
import 'word_database_repository.dart';
import 'analytics.dart';

class TaggingNotConfigured implements Exception {
  @override
  String toString() => '尚未設定 AI 辨識服務（設定 → AI 辨識服務）';
}

/// The spec's core loop, step 1 (選喜歡的照片): stores a picked or
/// captured photo. The original stays on the device (原圖留裝置); the
/// photo is queued for AI tagging (see TaggingQueue).
class PhotoIntake {
  final WordDatabaseRepository Function() repository;
  final PhotoStore photoStore;
  final TaggingService Function(Uri endpoint, String apiKey) createTagger;

  PhotoIntake({
    required this.repository,
    required this.photoStore,
    TaggingService Function(Uri endpoint, String apiKey)? createTagger,
  }) : createTagger = createTagger ??
            ((endpoint, apiKey) =>
                TaggingService(endpoint: endpoint, apiKey: apiKey));

  /// A stable fingerprint of a picture's bytes: 64-bit FNV-1a, hex. Not
  /// cryptographic — it only has to tell "the same file again" from a new
  /// one, without adding a dependency.
  static String hashBytes(Uint8List bytes) {
    var h = 0xcbf29ce484222325;
    for (final b in bytes) {
      h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF;
    }
    return '${bytes.length}-${h.toRadixString(16)}';
  }

  /// The learner's photo that already holds exactly these bytes, if any
  /// (spec §7 deferred 重複加入同一照片; the picker asks before adding a
  /// second copy). Bundled samples and pre-hash photos never match.
  Photo? findDuplicate(Uint8List bytes) {
    final hash = hashBytes(bytes);
    // allPhotos: a photo added a moment ago still awaits its safety check.
    return repository()
        .allPhotos
        .where((p) => p.contentHash != null && p.contentHash == hash)
        .firstOrNull;
  }

  Future<Photo> addPhoto(
    Uint8List bytes, {
    required String title,
    String? albumId,
    String? place,
  }) async {
    final repo = repository();
    final now = repo.clock();
    final id = 'photo-${now.microsecondsSinceEpoch}';
    final saved = await photoStore.save(id, bytes);
    final size = await _imageSize(bytes);
    final photo = Photo(
      id: id,
      albumId: albumId,
      title: title,
      place: place,
      takenAt: now,
      filePath: saved.filePath,
      storedKey: saved.storedKey,
      width: size?.$1,
      height: size?.$2,
      createdAt: now,
      taggingStatus: TaggingStatus.pending,
      safetyStatus: PhotoSafetyStatus.unchecked,
      contentHash: hashBytes(bytes),
    );
    repo.addPhoto(photo);
    Analytics.instance.capture('photo_added', {'in_album': albumId != null}, now);
    return photo;
  }

  static Future<(int, int)?> _imageSize(Uint8List bytes) async {
    try {
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final size = (frame.image.width, frame.image.height);
      frame.image.dispose();
      codec.dispose();
      return size;
    } catch (e) {
      debugPrint('Image size detection failed: $e');
      return null;
    }
  }

  /// The photo's bytes, for (re)tagging.
  Future<Uint8List?> bytesOf(Photo photo) async {
    if (photo.assetPath != null) {
      return (await rootBundle.load(photo.assetPath!)).buffer.asUint8List();
    }
    if (photo.filePath != null && !kIsWeb) {
      return File(photo.filePath!).readAsBytes();
    }
    if (photo.storedKey != null) {
      return photoStore.storedBytes(photo.storedKey!);
    }
    return null;
  }
}
