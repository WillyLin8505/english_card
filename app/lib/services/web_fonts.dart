import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart'
    show debugPrint, kIsWeb, visibleForTesting;
import 'package:flutter/services.dart' show FontLoader;
import 'package:http/http.dart' as http;

/// The family MFont's CJK fallbacks name first.
const webCjkFamily = 'Noto Sans TC';

/// Noto Sans TC (SIL OFL), subset to Big5 plus every character in the app's
/// packs and source, served by the web build itself (web/fonts/).
@visibleForTesting
const webCjkFontFiles = ['fonts/NotoSansTC-Regular.ttf', 'fonts/NotoSansTC-Bold.ttf'];

/// Flutter web can't use the computer's fonts, so the fallbacks in MFont
/// (Noto Sans TC, PingFang TC, Microsoft JhengHei) don't exist there and the
/// engine fetches Chinese glyphs from Google on first use: new Chinese shows
/// as boxes for a moment, and stays boxes offline (問題回報 #25). Loading the
/// bundled font before the first frame avoids both. Native apps keep using
/// the system's fonts.
Future<void> loadWebCjkFont({
  Duration timeout = const Duration(seconds: 8),
  Future<Uint8List?> Function(Uri uri)? fetch,
  Uri? base,
}) async {
  if (!kIsWeb && fetch == null) return;
  final get = fetch ?? _fetch;
  final root = base ?? Uri.base;
  try {
    final files = await Future.wait([
      for (final path in webCjkFontFiles) get(root.resolve(path)),
    ]).timeout(timeout);
    final loader = FontLoader(webCjkFamily);
    var any = false;
    for (final bytes in files) {
      if (bytes == null || bytes.isEmpty) continue;
      loader.addFont(Future.value(ByteData.sublistView(bytes)));
      any = true;
    }
    if (any) await loader.load();
  } catch (e) {
    debugPrint('loadWebCjkFont failed: $e');
    // Slow or missing: the engine's own Google fallback still works online.
  }
}

Future<Uint8List?> _fetch(Uri uri) async {
  final response = await http.get(uri);
  return response.statusCode == 200 ? response.bodyBytes : null;
}
