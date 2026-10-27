import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Downloads an audio clip's bytes; throws when it could not.
typedef AudioDownload = Future<List<int>> Function(Uri url);

/// Recordings kept on the device (問題回報 #684: 這聲音需要等很久的時間).
/// Server recordings (https://api.willylinai.com, through a tunnel to the
/// dictionary PC) used to be streamed again on every tap, so each first
/// sound waited for the network. Now each http(s) clip is downloaded once
/// into `audio_cache/` under the app's temporary directory, named by a hash
/// of its URL, and played from there; the oldest files go first once there
/// are more than [maxFiles] or [maxBytes].
class AudioFileCache {
  AudioFileCache({
    Future<Directory> Function()? directory,
    AudioDownload? download,
    this.maxFiles = 300,
    this.maxBytes = 50 * 1024 * 1024,
  })  : _directory = directory ?? _defaultDirectory,
        _download = download ?? _httpDownload;

  final Future<Directory> Function() _directory;
  final AudioDownload _download;
  final int maxFiles;
  final int maxBytes;

  Future<Directory>? _dir;
  // One download per URL, however many times it is asked for at once.
  final _pending = <String, Future<File?>>{};
  // URLs already on disk, so prefetching them again (each rebuild of a
  // word's details) does nothing.
  final _ready = <String>{};

  static Future<Directory> _defaultDirectory() async =>
      Directory('${(await getTemporaryDirectory()).path}/audio_cache');

  static Future<List<int>> _httpDownload(Uri url) async {
    final response = await http.get(url).timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw HttpException('HTTP ${response.statusCode}', uri: url);
    }
    return response.bodyBytes;
  }

  /// Whether [url] is a clip this cache keeps (an http(s) URL on a device;
  /// the web has no files, and bundled clips are already local).
  static bool handles(String? url) =>
      !kIsWeb &&
      url != null &&
      (url.startsWith('https://') || url.startsWith('http://'));

  /// The cached file name for [url]: two 32-bit hashes of it (FNV-1a and
  /// djb2, kept to 32 bits so this also compiles for the web), with the
  /// clip's extension so the platform player knows the format.
  static String fileName(String url) {
    var fnv = 0x811c9dc5, djb = 5381;
    for (final b in utf8.encode(url)) {
      fnv = ((fnv ^ b) * 0x01000193) & 0xFFFFFFFF;
      djb = ((djb * 33) + b) & 0xFFFFFFFF;
    }
    String hex(int v) => v.toRadixString(16).padLeft(8, '0');
    final hash = '${hex(fnv)}${hex(djb)}';
    final uri = Uri.tryParse(url);
    final name = uri?.queryParameters['path'] ?? uri?.path ?? '';
    final ext =
        RegExp(r'\.(mp3|m4a|aac|ogg|oga|opus|wav|webm)$', caseSensitive: false)
            .firstMatch(name)
            ?.group(0)
            ?.toLowerCase();
    return '$hash${ext ?? '.mp3'}';
  }

  Future<Directory> _cacheDir() => _dir ??= () async {
        final dir = await _directory();
        await dir.create(recursive: true);
        return dir;
      }();

  /// The local copy of [url], downloading it first when there is none.
  /// Null when [url] is not cached here or could not be downloaded, so the
  /// caller streams it as before. Never throws.
  Future<File?> file(String url) {
    if (!handles(url)) return Future.value(null);
    // A block, not `=> _pending.remove(url)`: whenComplete would wait on
    // the removed future, which is this one.
    return _pending[url] ??= _fetch(url).whenComplete(() {
      _pending.remove(url);
    });
  }

  /// Forgets which clips are on disk (問題回報 #824: memory warning); the
  /// files stay and are found again when played. Downloads under way go on.
  void releaseMemory() => _ready.clear();

  /// Starts downloading [url] in the background (opening a word's details,
  /// a review card's front) so playing it later does not wait.
  void prefetch(String? url) {
    if (!handles(url) || _ready.contains(url)) return;
    unawaited(file(url!));
  }

  Future<File?> _fetch(String url) async {
    try {
      final dir = await _cacheDir();
      final file = File('${dir.path}/${fileName(url)}');
      if (await file.exists() && await file.length() > 0) {
        // Recently played clips are kept longest.
        try {
          await file.setLastModified(DateTime.now());
        } catch (_) {}
        _ready.add(url);
        return file;
      }
      final bytes = await _download(Uri.parse(url));
      if (bytes.isEmpty) throw const FormatException('empty audio');
      final part = File('${file.path}.part');
      await part.writeAsBytes(bytes, flush: true);
      await part.rename(file.path);
      _ready.add(url);
      await _trim(dir);
      return file;
    } catch (e) {
      debugPrint('Audio cache: $url not downloaded: $e');
      return null;
    }
  }

  /// Deletes the oldest clips until at most [maxFiles] / [maxBytes] stay.
  Future<void> _trim(Directory dir) async {
    try {
      final files = <(File, int, DateTime)>[];
      await for (final f in dir.list()) {
        if (f is! File || f.path.endsWith('.part')) continue;
        final stat = await f.stat();
        files.add((f, stat.size, stat.modified));
      }
      var count = files.length;
      var bytes = files.fold<int>(0, (sum, f) => sum + f.$2);
      if (count <= maxFiles && bytes <= maxBytes) return;
      files.sort((a, b) => a.$3.compareTo(b.$3));
      for (final (f, size, _) in files) {
        if (count <= maxFiles && bytes <= maxBytes) break;
        try {
          await f.delete();
        } catch (_) {}
        count--;
        bytes -= size;
      }
    } catch (e) {
      debugPrint('Audio cache trim failed: $e');
    }
  }
}
