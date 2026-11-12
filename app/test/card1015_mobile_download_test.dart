// Card #1015 / 問題回報 #1537 (審查 4.2.3(ii)): the full dictionary (~62 MB)
// is not fetched over mobile data before the user says so.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> _pack(String version) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'senses': [
            {'id': 1, 'definition': 'fruit', 'native': '蘋果'}
          ],
          'examples': [],
        }
      ],
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late WordDatabaseRepository repo;
  late int requests;
  late int bodyListens;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('card1015-');
    Hive.init(directory.path);
    LexiconPack.instance.loadJson(_pack('bundled'));
    repo = WordDatabaseRepository();
    requests = 0;
    bodyListens = 0;
  });
  tearDown(() async {
    await Hive.close();
    LexiconPack.instance.clear();
    await directory.delete(recursive: true);
  });

  MockClient server() => MockClient.streaming((request, _) async {
        requests++;
        final body = utf8.encode(jsonEncode(_pack('v1')));
        final stream = Stream<List<int>>.fromIterable([body])
            .map((c) {
          bodyListens++;
          return c;
        });
        return http.StreamedResponse(stream, 200,
            contentLength: 62000000,
            headers: {'content-type': 'application/json'});
      });

  test('mobile data: asks first, sizes the pack, downloads after the tap',
      () async {
    final s = DictionarySync(client: server(), remote: true)
      ..onMobileOnly = () async => true;
    await s.start(AppSettings.inMemory(), () => repo);
    expect(s.mobileWaitBytes, 62000000);
    expect(s.downloading, isFalse);
    expect(s.downloadedBytes, 0);
    await s.allowMobileDownload();
    expect(s.mobileWaitBytes, isNull);
    expect(requests, greaterThan(1));
    s.dispose();
  });

  test('Wi-Fi: downloads at once, nothing is asked', () async {
    final s = DictionarySync(client: server(), remote: true)
      ..onMobileOnly = () async => false;
    await s.start(AppSettings.inMemory(), () => repo);
    expect(s.mobileWaitBytes, isNull);
    expect(bodyListens, greaterThan(0));
    s.dispose();
  });
}
