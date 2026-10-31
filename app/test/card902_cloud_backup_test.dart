import 'dart:convert';
import 'dart:typed_data';

import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/cloud_backup.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('login keeps the token; upload and download use it', () async {
    final seen = <String>[];
    final client = MockClient((req) async {
      seen.add('${req.method} ${req.url.path} ${req.headers['Authorization']}');
      if (req.url.path.endsWith('/login')) {
        return http.Response(jsonEncode({'token': 'tok'}), 200);
      }
      if (req.method == 'GET' && req.url.path.endsWith('/backup')) {
        return http.Response.bytes([1, 2, 3], 200);
      }
      return http.Response(jsonEncode({'exists': true}), 200);
    });
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test');
    final cloud = CloudBackup(settings, client: client);
    expect(cloud.available, isTrue);
    await cloud.login('a@x.com', 'password1');
    expect(settings.cloudSignedIn, isTrue);
    expect(settings.cloudEmail, 'a@x.com');
    await cloud.uploadBytes(Uint8List.fromList([9]));
    expect(await cloud.downloadBytes(), [1, 2, 3]);
    expect(seen.last, 'GET /api/account/backup Bearer tok');
  });

  test('a rejected token signs out and shows the server message', () async {
    final client = MockClient((req) async =>
        http.Response(jsonEncode({'detail': '登入已失效，請重新登入'}), 401,
            headers: {'content-type': 'application/json; charset=utf-8'}));
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test')
      ..setCloudAccount('old', 'a@x.com');
    final cloud = CloudBackup(settings, client: client);
    await expectLater(
        cloud.info(),
        throwsA(isA<CloudBackupException>()
            .having((e) => e.message, 'message', '登入已失效，請重新登入')));
    expect(settings.cloudSignedIn, isFalse);
  });
}
