import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/learning_card.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'cefr_lexicon.dart';

/// Client for the photo-tagging API in spec-01 section 2:
///
///   運算環境   Predator 上 Ollama + Qwen3-VL-4B（Q4）
///   本機 API   127.0.0.1:8765
///   可選連線   Cloudflare Tunnel
///   請求格式   Web: raw JPEG body + X-API-Key；原生: 可使用 multipart
///
/// The service is `tagger/tagging_server.py` in this repo. `/tag` is
/// stage 1 of the spec's recognition (labels with picture context).
/// Meanings, IPA, examples and translations come from the offline database.

/// What GET /health says.
class TaggerHealth {
  final String model;
  final bool ollama;

  /// Whether the X-API-Key we sent is right; null if the server didn't say.
  final bool? keyOk;

  const TaggerHealth({required this.model, required this.ollama, this.keyOk});
}

/// What /enrich returns. Everything except a dictionary IPA is written by
/// the AI, and the app marks it so.
class EnrichResult {
  final String? meaning;
  final String? definition;
  final String? ipa;
  final String? ipaSource;
  final List<({String text, String translation})> examples;
  final List<String> translations;

  const EnrichResult({
    this.meaning,
    this.definition,
    this.ipa,
    this.ipaSource,
    this.examples = const [],
    this.translations = const [],
  });

  factory EnrichResult.fromJson(Map<String, dynamic> j) {
    String? s(String k) {
      final v = (j[k] as String?)?.trim();
      return v == null || v.isEmpty ? null : v;
    }

    return EnrichResult(
      meaning: s('meaning'),
      definition: s('definition'),
      ipa: s('ipa'),
      ipaSource: s('ipaSource'),
      examples: [
        for (final e in (j['examples'] as List? ?? const []))
          if (e is Map && (e['text'] as String? ?? '').trim().isNotEmpty)
            (
              text: (e['text'] as String).trim(),
              translation: (e['translation'] as String? ?? '').trim(),
            ),
      ],
      translations: [
        for (final t in (j['translations'] as List? ?? const [])) '$t'.trim()
      ],
    );
  }
}

/// A short Chinese explanation of a tagging failure, for the UI.
String describeTaggingError(Object e, String url) {
  if (e is TaggingApiException) {
    return switch (e.statusCode) {
      401 => 'API Key 不正確（設定 → AI 辨識服務）',
      502 => 'AI 模型沒有回應，請確認 Ollama 已啟動',
      422 => '這張照片的辨識結果格式不完整，請稍後重新辨識',
      _ => e.message,
    };
  }
  if (e is http.ClientException) return '連不到 AI 辨識服務（$url），請確認服務已啟動';
  if (e is TimeoutException) return 'AI 辨識服務太久沒有回應，稍後會自動重試';
  return '$e';
}

/// True for failures that mean "the tagger can't be reached right now" —
/// the photo waits in the queue instead of failing (spec: 本機 AI 無法
/// 連線時，照片加入本機待處理佇列).
bool isOffline(Object e) =>
    e is http.ClientException ||
    e is TimeoutException ||
    (e is TaggingApiException && e.statusCode == 502);

class TaggingApiException implements Exception {
  final String message;
  final int? statusCode;

  TaggingApiException(this.message, {this.statusCode});

  @override
  String toString() => 'TaggingApiException($statusCode): $message';
}

/// Parses a /tag reply into candidates, correcting each level with the
/// local vocabulary list. Accepts `candidates`, `tags`, `words` or
/// `objects` lists; positions may be `point: [x, y]` or `x`/`y`, as
/// fractions (0–1) or on a 0–1000 grid.
List<WordCandidate> parseCandidates(
  Object? json, {
  required CefrLexicon lexicon,
  String? focus,
}) {
  final Object? list = switch (json) {
    final Map<String, dynamic> m =>
      m['candidates'] ?? m['tags'] ?? m['words'] ?? m['objects'],
    final List<dynamic> l => l,
    _ => null,
  };
  if (list is! List) return const [];
  double unit(Object? v) {
    final d = v is num ? v.toDouble() : 0.5;
    return (d > 1 ? d / 1000 : d).clamp(0.0, 1.0);
  }

  double? num01(Object? v) => v is num ? v.toDouble().clamp(0.0, 1.0) : null;

  final out = <WordCandidate>[];
  final seen = <String>{};
  for (final item in list) {
    if (item is! Map<String, dynamic>) continue;
    final raw = item['word'] ?? item['en'] ?? item['label'];
    if (raw is! String || raw.trim().isEmpty) continue;
    // stained_glass → stained glass (the model sometimes joins a phrase).
    final word = raw
        .trim()
        .toLowerCase()
        .replaceAll('_', ' ')
        .replaceAll(RegExp(r'\s+'), ' ');
    if (!seen.add(word)) continue;
    final p = item['point'];
    final LabelPoint point;
    if (p is List && p.length >= 2) {
      point = LabelPoint(unit(p[0]), unit(p[1]));
    } else if (item['x'] is num && item['y'] is num) {
      point = LabelPoint(unit(item['x']), unit(item['y']));
    } else {
      point = const LabelPoint(0.5, 0.5);
    }
    final pos = shortPos((item['pos'] as String?)?.trim().toLowerCase() ??
        (word.contains(' ') ? 'phrase' : 'noun'));
    final modelLevel = (item['cefr'] ?? item['level']) as String?;
    final resolved = lexicon.resolve(word, pos,
        modelLevel: modelLevel?.toUpperCase(),
        zipf: (item['zipf'] as num?)?.toDouble());
    out.add(WordCandidate(
      word: resolved.lemma ?? word,
      lemma: resolved.lemma ?? word,
      pos: pos,
      meaning: ((item['meaning'] ?? item['zh']) as String? ?? '').trim(),
      level: resolved.level,
      levelSource: resolved.source,
      modelLevel: modelLevel,
      zipf: resolved.zipf,
      ipa: item['ipa'] as String? ?? resolved.ipa,
      evidence: (item['evidence'] as String? ?? '').trim(),
      point: point,
      visualConfidence:
          num01(item['visualConfidence'] ?? item['visual_confidence']) ?? 0.7,
      usefulness: num01(item['usefulness']) ?? 0.5,
      inferred: item['inferred'] as bool? ?? false,
      focus: focus,
    ));
  }
  return out;
}

class TaggingService {
  /// e.g. http://127.0.0.1:8765/tag on this PC, or the Cloudflare Tunnel
  /// URL when the phone isn't on the same network as "Predator".
  final Uri endpoint;
  final String apiKey;
  final http.Client _client;

  /// A photo takes about 30 s on "Predator" and a word about 4 s; past
  /// these a request is given up and retried later, so nothing spins
  /// forever.
  static const tagTimeout = Duration(minutes: 2);
  static const enrichTimeout = Duration(minutes: 1);

  TaggingService({
    required this.endpoint,
    required this.apiKey,
    http.Client? client,
  }) : _client = client ?? http.Client();

  /// Stage 1 for one JPEG: the candidate pool, centred on [level].
  /// [focus] and [exclude] ask for more candidates of a kind the pool is
  /// short of.
  Future<List<WordCandidate>> candidates(
    Uint8List jpeg, {
    required String level,
    required CefrLexicon lexicon,
    String lang = 'en',
    String native = 'zh-TW',
    String? focus,
    List<String> exclude = const [],
    bool? asWeb,
  }) async {
    final uri = endpoint.replace(queryParameters: {
      ...endpoint.queryParameters,
      'level': level,
      'lang': lang,
      'native': native,
      if (focus != null) 'focus': focus,
      if (exclude.isNotEmpty) 'exclude': exclude.take(40).join(','),
    });
    final http.Response response;
    if (asWeb ?? kIsWeb) {
      response = await _client
          .post(uri,
              headers: {'X-API-Key': apiKey, 'Content-Type': 'image/jpeg'},
              body: jpeg)
          .timeout(tagTimeout);
    } else {
      final request = http.MultipartRequest('POST', uri)
        ..headers['X-API-Key'] = apiKey
        ..files.add(
            http.MultipartFile.fromBytes('image', jpeg, filename: 'photo.jpg'));
      response = await _client
          .send(request)
          .then(http.Response.fromStream)
          .timeout(tagTimeout);
    }
    return parseCandidates(_decode(response, 'tagging'),
        lexicon: lexicon, focus: focus);
  }

  /// Word data for [word]: native meaning, a definition, IPA, [examples]
  /// new example sentences, and translations of [translate].
  Future<EnrichResult> enrich({
    required String word,
    String? pos,
    String? meaning,
    String lang = 'en',
    String native = 'zh-TW',
    int examples = 6,
    List<String> translate = const [],
  }) async {
    final response = await _client
        .post(
          endpoint.resolve('/enrich'),
          headers: {'X-API-Key': apiKey, 'Content-Type': 'application/json'},
          body: jsonEncode({
            'word': word,
            'pos': pos,
            'meaning': meaning,
            'lang': lang,
            'native': native,
            'examples': examples,
            'translate': translate,
          }),
        )
        .timeout(enrichTimeout);
    return EnrichResult.fromJson(
        _decode(response, 'enrich') as Map<String, dynamic>);
  }

  Object? _decode(http.Response response, String what) {
    if (response.statusCode != 200) {
      throw TaggingApiException(
        '$what request failed: ${utf8.decode(response.bodyBytes, allowMalformed: true)}',
        statusCode: response.statusCode,
      );
    }
    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw TaggingApiException('response is not JSON: ${response.body}');
    }
  }

  /// GET /health next to the tag endpoint, sending the key so the server
  /// can say whether it's right.
  Future<TaggerHealth> checkHealth() async {
    final uri = endpoint.resolve('/health');
    final response = await _client.get(uri, headers: {'X-API-Key': apiKey});
    if (response.statusCode != 200) {
      throw TaggingApiException('health check failed: ${response.body}',
          statusCode: response.statusCode);
    }
    final j =
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    return TaggerHealth(
      model: j['model'] as String? ?? '?',
      ollama: j['ollama'] as bool? ?? false,
      keyOk: j['keyOk'] as bool?,
    );
  }

  void close() => _client.close();
}
