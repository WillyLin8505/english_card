import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import '../models/photo.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'local_vision.dart';
import 'photo_store.dart';
import 'tagging_service.dart';
import 'text_scan.dart';
import 'word_database_repository.dart';
import 'analytics.dart';

class TaggingNotConfigured implements Exception {
  @override
  String toString() => '這台裝置沒有照片辨識（設定 → 照片辨識）';
}

/// The spec's core loop, step 1 (選喜歡的照片): stores a picked or
/// captured photo. The original stays on the device (原圖留裝置); the
/// photo is queued for AI tagging (see TaggingQueue).
class PhotoIntake {
  final WordDatabaseRepository Function() repository;
  final PhotoStore photoStore;

  /// The server client (developer / web builds, 設定 → 照片辨識連線).
  final PhotoTagger Function(Uri endpoint, String apiKey) createTagger;

  /// The device's own recognizer (the published app, 問題回報 #265).
  final PhotoTagger Function() createLocalTagger;

  /// The device's text reader, for 找文字 (問題回報 #324).
  final PhotoTagger Function() createTextTagger;

  PhotoIntake({
    required this.repository,
    required this.photoStore,
    PhotoTagger Function(Uri endpoint, String apiKey)? createTagger,
    PhotoTagger Function()? createLocalTagger,
    PhotoTagger Function()? createTextTagger,
  })  : createTagger = createTagger ??
            ((endpoint, apiKey) =>
                TaggingService(endpoint: endpoint, apiKey: apiKey)),
        createLocalTagger = createLocalTagger ?? LocalVisionTagger.new,
        createTextTagger = createTextTagger ?? TextScanTagger.new;

  /// A stable fingerprint of a picture's bytes: 64-bit FNV-1a, hex. Not
  /// cryptographic — it only has to tell "the same file again" from a new
  /// one, without adding a dependency.
  static String hashBytes(Uint8List bytes) {
    // Two 32-bit halves so the web build (no exact 64-bit ints in
    // JavaScript) gives the same value as before: prime = 2^40 + 0x1b3.
    const base = 0x100000000;
    var hi = 0xcbf29ce4, lo = 0x84222325;
    for (final b in bytes) {
      lo ^= b;
      final low = lo * 0x1b3;
      final carry = low ~/ base;
      hi = (hi * 0x1b3 + carry + (lo % 0x1000000) * 0x100) % base;
      lo = low % base;
    }
    // The old code printed the signed 64-bit value ("-…" when the top bit
    // is set); keep that so saved hashes still match.
    var sign = '';
    if (hi >= 0x80000000) {
      sign = '-';
      final borrow = lo == 0 ? 0 : 1;
      lo = (base - lo) % base;
      hi = (base - hi - borrow) % base;
    }
    final hex = hi == 0
        ? lo.toRadixString(16)
        : '${hi.toRadixString(16)}${lo.toRadixString(16).padLeft(8, '0')}';
    return '${bytes.length}-$sign$hex';
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
    PhotoScanMode scanMode = PhotoScanMode.objects,
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
      scanMode: scanMode,
    );
    repo.addPhoto(photo);
    Analytics.instance
        .capture('photo_added', {'in_album': albumId != null}, now);
    return photo;
  }

  /// 卡片集 (card #323): saves a downloaded deck picture. Its labels come
  /// with the deck, so it is already tagged and safe — nothing is queued.
  /// Returns the word entries the picture created.
  Future<({Photo photo, List<WordEntry> created})> addDeckPicture(
    Uint8List bytes, {
    required String title,
    String? place,
    required List<WordCandidate> labels,
    String? credit,
    String? albumId,
  }) async {
    final repo = repository();
    final now = repo.clock();
    final id = 'photo-deck-${now.microsecondsSinceEpoch}';
    final saved = await photoStore.save(id, bytes);
    final size = await _imageSize(bytes);
    final photo = Photo(
      id: id,
      title: title,
      place: place,
      takenAt: now,
      filePath: saved.filePath,
      storedKey: saved.storedKey,
      width: size?.$1,
      height: size?.$2,
      createdAt: now,
      taggingStatus: TaggingStatus.done,
      safetyStatus: PhotoSafetyStatus.safe,
      contentHash: hashBytes(bytes),
      credit: credit,
      albumId: albumId,
    );
    return (photo: photo, created: repo.addDeckPhoto(photo, labels));
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
      return File(PhotoStore.localPath(photo.filePath!)).readAsBytes();
    }
    if (photo.storedKey != null) {
      return photoStore.storedBytes(photo.storedKey!);
    }
    return null;
  }
}
