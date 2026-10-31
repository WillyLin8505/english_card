import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'app_settings.dart';

/// Thrown with a message the learner can read as is.
class CloudBackupException implements Exception {
  final String message;
  const CloudBackupException(this.message);

  @override
  String toString() => message;
}

/// What the cloud holds for the signed-in account.
class CloudBackupInfo {
  final bool exists;
  final int size;
  final DateTime? updatedAt;
  const CloudBackupInfo(this.exists, this.size, this.updatedAt);
}

/// 帳號登入與跨裝置同步 (card #902, 問題回報 #1173): sign in with email, keep
/// one backup file (the same file 匯出備份 writes) under the account, and
/// restore it on another device. Card #910: talks to `/api/account/*` of the
/// fixed account server [accountUrl] (not the photo-recognition TAGGING_URL, so
/// the store build can sign in); the token lives in the Keychain via [AppSettings].
class CloudBackup {
  /// Production account API; `--dart-define=ACCOUNT_URL=` points a dev build at another.
  static const accountUrl =
      String.fromEnvironment('ACCOUNT_URL', defaultValue: 'https://api.willylinai.com');

  final AppSettings settings;
  final String baseUrl;
  final http.Client _client;

  CloudBackup(this.settings, {http.Client? client, String? baseUrl})
      : baseUrl = baseUrl ?? accountUrl,
        _client = client ?? http.Client();

  bool get available => baseUrl.trim().isNotEmpty;

  Uri _uri(String path) => Uri.parse(baseUrl).resolve('/api/account/$path');

  Map<String, String> get _auth =>
      {'Authorization': 'Bearer ${settings.cloudToken}'};

  Never _fail(http.BaseResponse r, [String? body]) {
    String? detail;
    try {
      detail = (jsonDecode(body ?? '') as Map)['detail'] as String?;
    } catch (_) {}
    if (r.statusCode == 401) settings.setCloudAccount('', '');
    throw CloudBackupException(detail ?? '雲端連線失敗（${r.statusCode}）');
  }

  Future<void> _post(String path, Map<String, Object?> body,
      {String? fallbackLabel}) async {
    final r = await _client
        .post(_uri(path),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body))
        .timeout(const Duration(seconds: 30));
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
    final data = jsonDecode(utf8.decode(r.bodyBytes)) as Map;
    final user = (data['user'] as Map?) ?? const {};
    final label = (user['email'] as String?) ??
        fallbackLabel ??
        (user['nickname'] as String?) ??
        '';
    settings.setCloudAccount('${data['token']}', label);
  }

  Future<void> _sign(String path, String email, String password) =>
      _post(path, {
        'email': email.trim(),
        'password': password,
        'nickname': email.trim().split('@').first,
      }, fallbackLabel: email.trim());

  Future<void> register(String email, String password) =>
      _sign('register', email, password);

  Future<void> login(String email, String password) =>
      _sign('login', email, password);

  /// ID token from Google; the server checks signature, audience and expiry,
  /// and reuses the account that already has the same email.
  Future<void> loginWithGoogle(String idToken, {String? name}) =>
      _post('google', {'id_token': idToken, if (name != null) 'nickname': name});

  Future<void> loginWithApple(String identityToken, {String? name}) =>
      _post('apple', {
        'identity_token': identityToken,
        'nickname': (name == null || name.isEmpty) ? 'Learner' : name,
      });

  /// App Review 5.1.1(v): deletes the account and its cloud backup on the server.
  Future<void> deleteAccount() async {
    final r = await _client
        .post(_uri('delete'), headers: _auth)
        .timeout(const Duration(seconds: 30));
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
    settings.setCloudAccount('', '');
  }

  Future<void> logout() async {
    if (settings.cloudSignedIn) {
      try {
        await _client
            .post(_uri('logout'), headers: _auth)
            .timeout(const Duration(seconds: 15));
      } catch (_) {}
    }
    settings.setCloudAccount('', '');
  }

  Future<CloudBackupInfo> info() async {
    final r = await _client
        .get(_uri('backup/info'), headers: _auth)
        .timeout(const Duration(seconds: 30));
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
    final m = jsonDecode(utf8.decode(r.bodyBytes)) as Map;
    final at = m['updated_at'];
    return CloudBackupInfo(
        m['exists'] == true,
        (m['size'] as num?)?.toInt() ?? 0,
        at is num
            ? DateTime.fromMillisecondsSinceEpoch(at.toInt() * 1000)
            : null);
  }

  /// Uploads a backup held in memory (the web, tests).
  Future<void> uploadBytes(Uint8List bytes) async {
    final r = await _client
        .post(_uri('backup'),
            headers: {..._auth, 'Content-Type': 'application/octet-stream'},
            body: bytes)
        .timeout(const Duration(minutes: 5));
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
  }

  /// Uploads a backup file without reading it into memory.
  Future<void> uploadFile(File file) async {
    final request = http.StreamedRequest('POST', _uri('backup'))
      ..headers.addAll({..._auth, 'Content-Type': 'application/octet-stream'})
      ..contentLength = await file.length();
    final sent = _client.send(request);
    await for (final chunk in file.openRead()) {
      request.sink.add(chunk);
    }
    await request.sink.close();
    final streamed = await sent.timeout(const Duration(minutes: 5));
    final r = await http.Response.fromStream(streamed);
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
  }

  /// Downloads the backup to [file].
  Future<void> downloadTo(File file) async {
    final streamed = await _client
        .send(http.Request('GET', _uri('backup'))..headers.addAll(_auth))
        .timeout(const Duration(minutes: 5));
    if (streamed.statusCode != 200) {
      _fail(streamed, await streamed.stream.bytesToString());
    }
    final sink = file.openWrite();
    try {
      await streamed.stream.pipe(sink);
    } finally {
      await sink.close();
    }
  }

  /// Downloads the backup into memory (the web, tests).
  Future<Uint8List> downloadBytes() async {
    final r = await _client
        .get(_uri('backup'), headers: _auth)
        .timeout(const Duration(minutes: 5));
    if (r.statusCode != 200) _fail(r, utf8.decode(r.bodyBytes));
    return r.bodyBytes;
  }
}
