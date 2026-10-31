import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/learning_card.dart';
import 'app_settings.dart';
import 'cloud_backup.dart';
import 'deck_library.dart';
import 'word_database_repository.dart';

/// 後台使用者頁的數字 (card #911): once a day, a signed-in app sends counts and the
/// names of the downloaded photo albums to its own account server. Never photo or
/// word content; nothing is sent while signed out, and any failure is ignored (the
/// next start retries) so offline use is unaffected.
class UsageReport {
  static const appVersion =
      String.fromEnvironment('APP_VERSION', defaultValue: '1.0.0+1');
  static const minGap = Duration(hours: 20);

  final AppSettings settings;
  final WordDatabaseRepository repository;
  final http.Client _client;
  final String baseUrl;
  final DateTime Function() _now;

  UsageReport(this.settings, this.repository,
      {http.Client? client, String? baseUrl, DateTime Function()? now})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? CloudBackup.accountUrl,
        _now = now ?? DateTime.now;

  /// The numbers only. Review counts come from the ReviewLog timestamps.
  Map<String, Object?> snapshot() {
    final now = _now();
    final weekAgo = now.subtract(const Duration(days: 7));
    final List<ReviewLog> logs = repository.recentReviewLogs(1 << 30);
    return {
      'albums': [
        for (final d in DeckLibrary.instance.installed)
          if (d.info.kind == 'photos') d.info.title
      ],
      'reviews_total': logs.length,
      'reviews_7d': logs.where((l) => l.reviewedAt.isAfter(weekAgo)).length,
      'photos_taken': repository.allPhotos.length,
      'photos_opened': settings.usageCount('photosOpened'),
      'app_version': appVersion,
    };
  }

  /// Sends when signed in and the last success is older than [minGap] (or [force]).
  /// Returns whether the server took it.
  Future<bool> sendIfDue({bool force = false}) async {
    if (!settings.cloudSignedIn || baseUrl.trim().isEmpty) return false;
    final nowMs = _now().millisecondsSinceEpoch;
    if (!force && nowMs - settings.statsSentAt < minGap.inMilliseconds) {
      return false;
    }
    try {
      final r = await _client
          .post(Uri.parse(baseUrl).resolve('/api/account/stats'),
              headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ${settings.cloudToken}',
              },
              body: jsonEncode(snapshot()))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return false;
      settings.statsSentAt = nowMs;
      return true;
    } catch (_) {
      return false;
    }
  }
}
