import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/background_errors.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_enricher.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'helpers.dart' show testLexicon;

Map<String, dynamic> pack(String version, String meaning,
        {String native = 'zh-TW'}) =>
    {
      'target_language': 'en',
      'native_language': native,
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
            {'id': 1, 'definition': 'fruit', 'native': meaning}
          ],
          'examples': [
            {'text': 'An apple.', 'translation': '$meaning。', 'level': 'A1'}
          ],
          'relations': [
            {
              'relation': 'synonyms',
              'word': 'pome',
              'native': '梨果',
              'cefr': 'C2',
              'hide_by_default': true
            },
            {
              'relation': 'related',
              'word': 'potato',
              'native': '馬鈴薯',
              'cefr': 'A1'
            },
            {'relation': 'synonyms', 'word': 'untranslated', 'cefr': 'A1'},
          ],
        }
      ],
    };
http.Response response(Map<String, dynamic> p) =>
    http.Response.bytes(utf8.encode(jsonEncode(p)), 200);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late WordDatabaseRepository repo;
  late String id;
  final services = <DictionarySync>[];
  test('new words use the current dictionary even without a new server version',
      () async {
    final enricher = WordEnricher(
      repository: () => repo,
      settings: AppSettings.inMemory(),
      intake: PhotoIntake(
          repository: () => repo, photoStore: PhotoStore.inMemory()),
      lexicon: testLexicon,
    );
    await enricher.process();
    expect(repo.entry(id)!.meaning, '蘋果');
    expect(repo.entry(id)!.examples, hasLength(1));
    expect(repo.entry(id)!.dataStatus, WordDataStatus.complete);
    expect(repo.entry(id)!.dataError, isNull);
    enricher.dispose();
  });
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('dictionary-sync-test-');
    Hive.init(directory.path);
    LexiconPack.instance.loadJson(pack('bundled', '蘋果'));
    repo = WordDatabaseRepository();
    id = repo.addWord(word: 'apple', pos: 'noun', meaning: '舊意思').id;
  });
  tearDown(() async {
    for (final s in services) {
      s.dispose();
    }
    services.clear();
    await Hive.close();
    LexiconPack.instance.clear();
    await directory.delete(recursive: true);
  });
  DictionarySync service(http.Client client) {
    final s = DictionarySync(client: client);
    services.add(s);
    return s;
  }

  test(
      'live correction replaces stale data, preserves manual edits and review history',
      () async {
    var p = pack('1', '最新蘋果');
    final s = service(MockClient((_) async => response(p)));
    final settings = AppSettings.inMemory();
    await s.start(settings, () => repo);
    expect(repo.entry(id)!.meaning, '最新蘋果');
    final card = repo.cardOf(id)!;
    repo.review(card.id, Rating.good);
    final due = repo.cardOf(id)!.fsrs.due;
    repo.editEntry(
        repo.entry(id)!.copyWith(meaning: '我的蘋果'), {WordField.meaning});
    p = pack('2', '後台修訂');
    await s.refresh();
    expect(repo.entry(id)!.meaning, '我的蘋果');
    expect(repo.entry(id)!.examples.single.translation, '後台修訂。');
    expect(repo.logsOf(card.id), hasLength(1));
    expect(repo.cardOf(id)!.fsrs.due, due);
  });

  test(
      'offline restart uses persistent cache; malformed/wrong-language responses do not replace it',
      () async {
    var mode = 0;
    final client = MockClient((_) async {
      if (mode == 1) throw const SocketException('offline');
      if (mode == 2) return response(pack('bad', 'pomme', native: 'fr'));
      return response(pack('saved', '快取蘋果'));
    });
    final s = service(client);
    await s.start(AppSettings.inMemory(), () => repo);
    mode = 1;
    await s.refresh();
    expect(s.status, contains('使用已儲存'));
    expect(repo.entry(id)!.meaning, '快取蘋果');
    mode = 2;
    await s.refresh();
    expect(repo.entry(id)!.meaning, '快取蘋果');
    LexiconPack.instance.clear();
    final restarted = service(
        MockClient((_) async => throw const SocketException('offline')));
    await restarted.start(AppSettings.inMemory(), () => repo);
    expect(LexiconPack.instance.lookup('apple')!.entry.nativeMeaning, '快取蘋果');
  });

  test(
      '問題回報 #175: a failed refresh reaches BackgroundErrors with a retry, '
      'and a later success clears it', () async {
    var mode = 0;
    final client = MockClient((_) async {
      if (mode == 1) throw const SocketException('offline');
      return response(pack('v1', '蘋果'));
    });
    final s = service(client);
    await s.start(AppSettings.inMemory(), () => repo);
    expect(BackgroundErrors.instance.message, isNull);
    mode = 1;
    await s.refresh();
    expect(BackgroundErrors.instance.message, contains('無法連線'));
    expect(BackgroundErrors.instance.retry, isNotNull);
    mode = 0;
    await BackgroundErrors.instance.retry!();
    expect(BackgroundErrors.instance.message, isNull);
  });

  test('304 keeps content and sends the cached version', () async {
    var calls = 0;
    final s = service(MockClient((request) async {
      if (calls++ == 0) return response(pack('v1', '蘋果'));
      expect(request.headers['If-None-Match'], '"v1"');
      return http.Response('', 304);
    }));
    await s.start(AppSettings.inMemory(), () => repo);
    await s.refresh();
    expect(s.status, contains('已連接'));
    expect(repo.entry(id)!.meaning, '蘋果');
  });

  test('incremental sync persists a full snapshot and restart revalidates it',
      () async {
    var calls = 0;
    final updated = pack('v2', '增量蘋果');
    final s = service(MockClient((request) async {
      if (calls++ == 0) return response(pack('v1', '蘋果'));
      expect(request.url.queryParameters['since'], 'v1');
      expect(request.headers['If-None-Match'], '"v1"');
      return response({
        'delta_version': 1,
        'base_version': 'v1',
        'metadata': {...updated}..remove('lexemes'),
        'order': [1],
        'upserts': updated['lexemes'],
      });
    }));
    await s.start(AppSettings.inMemory(), () => repo);
    await s.refresh();
    expect(repo.entry(id)!.meaning, '增量蘋果');
    expect(jsonDecode(Hive.box<String>('dictionary_cache_v1').get('en-zh-TW')!),
        updated);
    LexiconPack.instance.clear();
    final restarted = service(MockClient((request) async {
      expect(request.url.queryParameters['since'], 'v2');
      expect(request.headers['If-None-Match'], '"v2"');
      return http.Response('', 304);
    }));
    await restarted.start(AppSettings.inMemory(), () => repo);
    expect(LexiconPack.instance.lookup('apple')!.entry.nativeMeaning, '增量蘋果');
    expect(restarted.status, contains('已連接'));
  });

  test('wrong delta base retains content and next request recovers in full',
      () async {
    var calls = 0;
    final s = service(MockClient((request) async {
      if (calls++ == 0) return response(pack('v1', '蘋果'));
      if (calls == 2) {
        return response({'delta_version': 1, 'base_version': 'wrong'});
      }
      expect(request.url.queryParameters.containsKey('since'), false);
      expect(request.headers.containsKey('If-None-Match'), false);
      return response(pack('v2', '恢復蘋果'));
    }));
    await s.start(AppSettings.inMemory(), () => repo);
    await s.refresh();
    expect(repo.entry(id)!.meaning, '蘋果');
    await s.refresh();
    expect(repo.entry(id)!.meaning, '恢復蘋果');
  });

  test('delta handles deletions, ordering and rejects incomplete rows', () {
    final base = {'created_at': 'v1', 'lexemes': [
      {'id': 1}, {'id': 2}, {'id': 3},
    ]};
    final patch = {
      'delta_version': 1, 'base_version': 'v1',
      'metadata': {'created_at': 'v2'},
      'order': [3, 4, 1], 'upserts': [{'id': 4, 'meaning': 'new'}],
    };
    expect(applyDictionaryDelta(base, patch)['lexemes'], [
      {'id': 3}, {'id': 4, 'meaning': 'new'}, {'id': 1},
    ]);
    expect(() => applyDictionaryDelta(base, {...patch, 'order': [9]}),
        throwsFormatException);
  });

  test('late response cannot overwrite a newly selected language', () async {
    final slow = Completer<http.Response>();
    var calls = 0;
    final s = service(MockClient((r) async {
      calls++;
      if (r.url.queryParameters['native'] == 'zh-TW') return slow.future;
      return response(pack('fr1', 'pomme', native: 'fr'));
    }));
    final settings = AppSettings.inMemory();
    final first = s.start(settings, () => repo);
    while (calls == 0) {
      await Future<void>.delayed(Duration.zero);
    }
    settings.nativeLanguage = 'fr';
    slow.complete(response(pack('late', '不應出現')));
    await first;
    for (var i = 0; i < 30 && repo.entry(id)!.meaning != 'pomme'; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    expect(repo.entry(id)!.meaning, 'pomme');
  });

  test('learning UI rejects rare, untranslated and untyped associations', () {
    repo.linkLexicon(LexiconPack.instance);
    expect(learningRelations(repo.entry(id)!, 'A1', 'synonyms'), isEmpty);
    final e = repo.entry(id)!.copyWith(examples: [
      const WordExample(text: 'No translation.'),
      const WordExample(
          text: 'This is a much longer sentence.', translation: '較長句子'),
      const WordExample(text: 'An apple.', translation: '一顆蘋果'),
    ]);
    expect(learningExamples(e, 'A1').first.text, 'An apple.');
    expect(learningExamples(e, 'A1'), hasLength(2));
  });
}
