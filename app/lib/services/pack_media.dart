import 'package:flutter/foundation.dart' show kIsWeb;

/// A pack media path the device can actually load (問題回報 #270).
///
/// Live packs store server paths (`/api/audio`, `/api/image?id=`). On the
/// web those resolve against the page. On a phone [Uri.base] is a file URI,
/// so the same path is resolved against the dictionary server — the same
/// origin as [DictionarySync.endpoint]. Bundled files stay `assets/…` for
/// [Image.asset] and audioplayers [AssetSource].
String resolvePackMedia(String path) {
  if (path.startsWith('assets/')) return path;
  final parsed = Uri.tryParse(path);
  if (parsed != null && parsed.hasScheme) return path;
  if (kIsWeb) return Uri.base.resolve(path).toString();
  const configured = String.fromEnvironment('DICTIONARY_URL');
  final origin = configured.isNotEmpty
      ? Uri.parse(configured)
      : Uri.parse('https://api.willylinai.com/');
  return origin.resolve(path).toString();
}

bool packMediaIsAsset(String path) => path.startsWith('assets/');

/// Recording URL for [relativePath] (for example `audio/en/go.mp3`).
/// No [mediaBase] means the clip is bundled under `assets/lexicon/media/`.
String packRecordingUrl(String? mediaBase, String relativePath) {
  if (mediaBase == null) return 'assets/lexicon/media/$relativePath';
  return Uri.parse(resolvePackMedia(mediaBase))
      .replace(queryParameters: {'path': relativePath})
      .toString();
}
