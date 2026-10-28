import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/photo.dart';
import 'app_settings.dart';

/// 問題回報 #853 (card #724, owner 2026-10-28): the owner's own developer-build
/// phone sends every photo it recognizes, with its labels, to 後台 so the
/// picture can be seen there. The store build has no server address and never
/// uploads: it needs [AppSettings.developerTools] and a server address.
class DevPhotoUpload {
  DevPhotoUpload._();

  static bool enabled(AppSettings settings) =>
      !kIsWeb &&
      AppSettings.developerTools &&
      !settings.usesLocalRecognition &&
      settings.taggingUrl.trim().isNotEmpty;

  /// Best effort: a failure is ignored, the next recognition sends it again.
  static Future<bool> send(
    AppSettings settings,
    Photo photo,
    Uint8List jpeg, {
    String language = 'en',
    http.Client? client,
  }) async {
    if (!enabled(settings)) return false;
    final http.Client uploader = client ?? http.Client();
    try {
      final response = await uploader
          .post(
            Uri.parse(settings.taggingUrl).resolve('/api/app-photo'),
            headers: {
              'X-API-Key': settings.apiKey,
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'photo_id': photo.id,
              'title': photo.title,
              'device': defaultTargetPlatform.name,
              'language': language,
              'image_b64': base64Encode(jpeg),
              'labels': [
                for (final c in photo.candidates)
                  {
                    'word': c.word,
                    'pos': c.pos,
                    'cefr': c.level,
                    'meaning': c.meaning,
                    'point': c.point.toJson(),
                  },
              ],
            }),
          )
          .timeout(const Duration(seconds: 60));
      return response.statusCode == 201;
    } catch (_) {
      return false;
    } finally {
      if (client == null) uploader.close();
    }
  }
}
