import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:path_provider/path_provider.dart';

import '../../models/photo.dart';
import '../../services/photo_store.dart';

// How photos are loaded (card #252: 照片載入有時候需要時間). Before, every
// photo was decoded at its original size — a 12 MP photo is ~48 MB once
// decoded, so the default 100 MB ImageCache held two and kept evicting and
// re-decoding them; web photos were reread from Hive and decoded again on
// every mount (MemoryImage keys on the byte list's identity, so it never
// hit the cache); and on phones network photos had no byte cache at all.
// Now each photo is decoded at the size it is shown (rounded up to a few
// widths so screens share cache entries), stored photos have a stable cache
// key, and network bytes are kept on disk.

/// Decode widths in pixels. A photo is decoded at the first one at least
/// as wide as it is shown, so near-equal boxes share one cache entry.
const photoDecodeWidths = [128, 256, 384, 512, 768, 1024, 1536, 2048];

int photoDecodeBucket(double px) => photoDecodeWidths.firstWhere((w) => px <= w,
    orElse: () => photoDecodeWidths.last);

/// The width in pixels to decode [photo] at so it fills [box] with [fit]
/// on a screen with [dpr]; null when the box has no finite size.
int? photoDecodeWidth(Photo photo, Size box, double dpr,
    {BoxFit fit = BoxFit.cover}) {
  if (!box.width.isFinite || !box.height.isFinite || box.isEmpty) return null;
  final w = photo.width?.toDouble(), h = photo.height?.toDouble();
  if (w == null || h == null || w <= 0 || h <= 0) {
    // Unknown shape: wide enough for a 3:2 photo to cover the box.
    return photoDecodeBucket(math.max(box.width, box.height) * dpr * 1.5);
  }
  final sx = box.width / w, sy = box.height / h;
  final contain = fit == BoxFit.contain || fit == BoxFit.scaleDown;
  return photoDecodeBucket(
      w * (contain ? math.min(sx, sy) : math.max(sx, sy)) * dpr);
}

/// The full-size pixels of [photo]; null for a photo without an image
/// (or a stored one with no [store] to read it from).
ImageProvider<Object>? photoSource(Photo photo, PhotoStore? store) {
  if (photo.assetPath != null) return AssetImage(photo.assetPath!);
  if (photo.networkUrl != null) {
    // The browser keeps its own HTTP cache.
    if (kIsWeb) return NetworkImage(photo.networkUrl!);
    return CachedNetworkPhoto(photo.networkUrl!);
  }
  if (photo.filePath != null && !kIsWeb) {
    return FileImage(File(PhotoStore.localPath(photo.filePath!)));
  }
  if (photo.storedKey != null && store != null) {
    return StoredPhotoImage(store, photo.storedKey!);
  }
  return null;
}

/// [photo] decoded for a [box] of that size (see [photoDecodeWidth]).
ImageProvider<Object>? photoProvider(
    Photo photo, PhotoStore? store, Size box, double dpr,
    {BoxFit fit = BoxFit.cover}) {
  final source = photoSource(photo, store);
  if (source == null) return null;
  final width = photoDecodeWidth(photo, box, dpr, fit: fit);
  return width == null ? source : ResizeImage(source, width: width);
}

/// Starts loading [photo] for a [box] of that size before it is shown —
/// e.g. the card back's photo while the learner is still on the front.
Future<void> precachePhoto(
    BuildContext context, Photo photo, PhotoStore? store, Size box,
    {BoxFit fit = BoxFit.cover}) async {
  final dpr = MediaQuery.maybeDevicePixelRatioOf(context) ?? 1;
  final provider = photoProvider(photo, store, box, dpr, fit: fit);
  if (provider == null) return;
  await precacheImage(provider, context, onError: (_, __) {});
}

/// A failed load must not stay in the ImageCache, or a retry would get
/// the same error (NetworkImage does the same).
Future<ui.Codec> _evictOnError(
    Object key, Future<ui.Codec> Function() load) async {
  try {
    return await load();
  } catch (_) {
    scheduleMicrotask(() => PaintingBinding.instance.imageCache.evict(key));
    rethrow;
  }
}

/// A photo kept in [PhotoStore] (web). Keyed by store and key, so the
/// decoded image is shared across rebuilds, remounts and screens.
@immutable
class StoredPhotoImage extends ImageProvider<StoredPhotoImage> {
  final PhotoStore store;
  final String storedKey;

  const StoredPhotoImage(this.store, this.storedKey);

  @override
  Future<StoredPhotoImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(
          StoredPhotoImage key, ImageDecoderCallback decode) =>
      MultiFrameImageStreamCompleter(
          codec: _evictOnError(key, () async {
            final bytes = await store.storedBytes(storedKey);
            if (bytes == null || bytes.isEmpty) {
              throw StateError('stored photo $storedKey is missing');
            }
            return decode(await ui.ImmutableBuffer.fromUint8List(bytes));
          }),
          scale: 1,
          debugLabel: 'stored:$storedKey');

  @override
  bool operator ==(Object other) =>
      other is StoredPhotoImage &&
      identical(other.store, store) &&
      other.storedKey == storedKey;

  @override
  int get hashCode => Object.hash(identityHashCode(store), storedKey);

  @override
  String toString() => 'StoredPhotoImage("$storedKey")';
}

/// A network photo whose bytes are kept in the app's cache folder, so a
/// photo seen once loads from disk next time (phones and desktop).
@immutable
class CachedNetworkPhoto extends ImageProvider<CachedNetworkPhoto> {
  final String url;

  const CachedNetworkPhoto(this.url);

  /// Most files kept; the oldest go first.
  static int maxFiles = 400;

  @visibleForTesting
  static Future<Directory?> Function() cacheDirectory = _defaultDirectory;

  @visibleForTesting
  static Future<Uint8List> Function(Uri url) fetch = _httpGet;

  static Future<Directory?> _defaultDirectory() async {
    // Widget tests run on fake time, where real file I/O never completes.
    if (Platform.environment.containsKey('FLUTTER_TEST')) return null;
    final base = await getApplicationCacheDirectory();
    return Directory('${base.path}${Platform.pathSeparator}photo_cache');
  }

  // HttpClient as NetworkImage uses it (tests' HTTP overrides apply too).
  static final _client = HttpClient()..autoUncompress = false;

  static Future<Uint8List> _httpGet(Uri url) async {
    final response = await (await _client.getUrl(url)).close();
    if (response.statusCode != HttpStatus.ok) {
      await response.drain<void>();
      throw NetworkImageLoadException(
          statusCode: response.statusCode, uri: url);
    }
    final bytes = await consolidateHttpClientResponseBytes(response);
    if (bytes.isEmpty) throw StateError('empty image: $url');
    return bytes;
  }

  /// A file name for [url]: two 32-bit FNV-1a hashes.
  @visibleForTesting
  static String fileName(String url) {
    var a = 0x811c9dc5, b = 0x050c5d1f;
    for (final c in url.codeUnits) {
      a = ((a ^ c) * 0x01000193) & 0xffffffff;
      b = ((b ^ c) * 0x01000193) & 0xffffffff;
    }
    return '${a.toRadixString(16).padLeft(8, '0')}'
        '${b.toRadixString(16).padLeft(8, '0')}.img';
  }

  static int _writes = 0;

  /// Downloads under way, by URL (問題回報 #702): the review screen warms a
  /// photo at two or three decode sizes at once, and each size used to
  /// download the whole file again (a 1280 px picture is ~400 KB).
  static final _inFlight = <String, Future<Uint8List>>{};

  /// Waits before trying a failed download again (問題回報 #702: one
  /// dropped connection left 「圖片暫時無法載入」 on the card for good).
  @visibleForTesting
  static List<Duration> retryDelays = const [
    Duration(milliseconds: 600),
    Duration(milliseconds: 1800),
  ];

  /// A failure worth another try: the connection, a timeout, or the server
  /// busy (429 / 5xx). A 404 stays a 404.
  @visibleForTesting
  static bool isTransient(Object error) =>
      error is SocketException ||
      error is HttpException ||
      error is TimeoutException ||
      error is HandshakeException ||
      (error is NetworkImageLoadException &&
          (error.statusCode == 429 || error.statusCode >= 500));

  static Future<Uint8List> _fetchRetrying(Uri url) async {
    for (var attempt = 0;; attempt++) {
      try {
        return await fetch(url);
      } catch (e) {
        if (attempt >= retryDelays.length || !isTransient(e)) rethrow;
        await Future<void>.delayed(retryDelays[attempt]);
      }
    }
  }

  /// The bytes of [url]: from disk when cached, else downloaded and kept.
  /// Asked again while it is downloading, the same download is shared.
  @visibleForTesting
  static Future<Uint8List> bytesFor(String url) {
    final running = _inFlight[url];
    if (running != null) return running;
    final load = _bytesFor(url);
    _inFlight[url] = load;
    load.whenComplete(() => _inFlight.remove(url)).ignore();
    return load;
  }

  /// Downloads [url] to the cache folder without decoding it (問題回報
  /// #726): the cards further ahead in a review get their photos onto the
  /// phone early, without holding decoded pixels in memory. Never throws.
  static void prefetch(String url) {
    if (kIsWeb || !_prefetched.add(url)) return;
    bytesFor(url).then<void>((_) {}, onError: (_) {
      _prefetched.remove(url);
    });
  }

  // URLs already fetched by [prefetch], so each review card does not read
  // them from disk again.
  static final _prefetched = <String>{};

  static Future<Uint8List> _bytesFor(String url) async {
    File? file;
    try {
      final dir = await cacheDirectory();
      if (dir == null) throw const FileSystemException('no cache folder');
      file = File('${dir.path}${Platform.pathSeparator}${fileName(url)}');
      if (await file.exists()) {
        final bytes = await file.readAsBytes();
        if (bytes.isNotEmpty) return bytes;
      }
    } catch (_) {
      file = null; // No cache folder: still show the photo.
    }
    final bytes = await _fetchRetrying(Uri.parse(url));
    if (file != null) unawaited(_keep(file, bytes));
    return bytes;
  }

  static Future<void> _keep(File file, Uint8List bytes) async {
    try {
      await file.parent.create(recursive: true);
      // Written beside, then renamed: a half-written file is never read.
      final part = File('${file.path}.part');
      await part.writeAsBytes(bytes, flush: true);
      await part.rename(file.path);
      if (++_writes % 50 == 1) await _prune(file.parent);
    } catch (_) {}
  }

  static Future<void> _prune(Directory dir) async {
    final files = [
      await for (final f in dir.list())
        if (f is File && f.path.endsWith('.img')) f,
    ];
    if (files.length <= maxFiles) return;
    final dated = [for (final f in files) (f, await f.lastModified())]
      ..sort((x, y) => x.$2.compareTo(y.$2));
    for (final (f, _) in dated.take(files.length - maxFiles)) {
      await f.delete();
    }
  }

  @override
  Future<CachedNetworkPhoto> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(
          CachedNetworkPhoto key, ImageDecoderCallback decode) =>
      MultiFrameImageStreamCompleter(
          codec: _evictOnError(
              key,
              () async => decode(
                  await ui.ImmutableBuffer.fromUint8List(await bytesFor(url)))),
          scale: 1,
          debugLabel: url);

  @override
  bool operator ==(Object other) =>
      other is CachedNetworkPhoto && other.url == url;

  @override
  int get hashCode => url.hashCode;

  @override
  String toString() => 'CachedNetworkPhoto("$url")';
}
