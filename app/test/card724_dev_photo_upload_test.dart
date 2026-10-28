import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dev_photo_upload.dart';

void main() {
  final photo = Photo(
      id: 'photo-1',
      title: 'desk',
      takenAt: DateTime(2026, 10, 28),
      createdAt: DateTime(2026, 10, 28));

  test('no server address (store build): nothing is sent', () async {
    var calls = 0;
    final client = MockClient((r) async {
      calls++;
      return http.Response('{}', 201);
    });
    final settings = AppSettings.inMemory();
    final sent = await DevPhotoUpload.send(
        settings, photo, Uint8List.fromList([1, 2, 3]),
        client: client);
    expect(sent, isFalse);
    expect(calls, 0);
  });

  test('store build with a server address still sends nothing', () async {
    // developerTools is a compile-time flag (DEV_TOOLS); without it no photo leaves.
    if (AppSettings.developerTools) return;
    var calls = 0;
    final client = MockClient((r) async {
      calls++;
      return http.Response('{}', 201);
    });
    final settings = AppSettings.inMemory()
      ..taggingUrl = 'http://192.168.0.2:8123/tag';
    expect(DevPhotoUpload.enabled(settings), isFalse);
    expect(
        await DevPhotoUpload.send(settings, photo, Uint8List.fromList([1]),
            client: client),
        isFalse);
    expect(calls, 0);
  });

  test('developer build posts the photo and labels to /api/app-photo',
      () async {
    if (!AppSettings.developerTools) return;
    late http.Request seen;
    final client = MockClient((r) async {
      seen = r;
      return http.Response('{}', 201);
    });
    final settings = AppSettings.inMemory()
      ..taggingUrl = 'http://192.168.0.2:8123/tag';
    final sent = await DevPhotoUpload.send(
        settings, photo, Uint8List.fromList([0xff, 0xd8, 0xff]),
        client: client);
    expect(sent, isTrue);
    expect(seen.url.path, '/api/app-photo');
    expect(jsonDecode(seen.body)['photo_id'], 'photo-1');
  });
}
