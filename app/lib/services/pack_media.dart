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
      .replace(queryParameters: {'path': relativePath}).toString();
}

/// The longest side asked of the server for a catalog picture (問題回報
/// #859). Wide enough for a phone's full width at 3× (402 pt × 3 = 1206 px)
/// with room for [BoxFit.cover]; one size for every place a picture shows,
/// so the front, the back's carousel and the dictionary share one download
/// and one file in the disk cache.
const servedImageSide = 1536;

/// [url] asking the server for its downscaled copy (`/api/image?id=…&w=`,
/// longest side ≤ [side]; the server sends the original when it is smaller
/// already). Other URLs, and ones that already ask a size, are unchanged.
String sizedServerImage(String url, {int side = servedImageSide}) {
  final uri = Uri.tryParse(url);
  if (uri == null || !uri.path.endsWith('/api/image')) return url;
  final query = uri.queryParameters;
  if (const ['w', 'max', 'size'].any(query.containsKey)) return url;
  return uri.replace(queryParameters: {...query, 'w': '$side'}).toString();
}

/// The server's small copy of a picture [sizedServerImage] asked at
/// [servedImageSide] (問題回報 #938): for tiles and covers drawn ≤ 512 px.
/// Other URLs are unchanged.
String thumbServerImage(String url, {int side = 480}) {
  final uri = Uri.tryParse(url);
  if (uri == null || !uri.path.endsWith('/api/image')) return url;
  if (uri.queryParameters['w'] != '$servedImageSide') return url;
  return uri.replace(queryParameters: {...uri.queryParameters, 'w': '$side'})
      .toString();
}
