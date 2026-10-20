// Card #428 (問題回報 #423, owner decision B): the language pack as SQLite.
// A SQLite pack must behave exactly like the JSON pack it was built from,
// while only the heads are parsed at load time.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show FlutterError;
import 'package:flutter/services.dart' show AssetBundle;
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

Map<String, dynamic> pack({String version = 'v1', String meaning = '蘋果'}) => {
      'schema_version': 5,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'media_base': '/api/audio',
      'catalog_version': 1,
      'labels': {'pos:noun': '名詞'},
      'redirects': {'99': 1},
      'catalog_images': [
        {
          'id': 7,
          'url': '/api/image?id=7',
          'tags': [
            {'lexeme_id': 1, 'sense_id': 10, 'review_status': 'approved'}
          ]
        }
      ],
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'zipf': 4.8,
          'senses': [
            {
              'id': 10,
              'definition': 'A round fruit.',
              'register': 'spoken',
              'native': meaning,
              'native_ai': false
            },
          ],
          'forms': [
            {
              'field': 'noun_plural',
              'form': 'apples',
              'normalized': 'apples',
              'label': '名詞複數'
            },
          ],
          'pronunciations': [
            {'kind': 'ipa', 'value': '/ˈæp.əl/', 'accent': 'US'},
            {
              'kind': 'audio',
              'audio': 'audio/en/abc.mp3',
              'default': true,
              'license': 'CC BY-SA 4.0'
            },
          ],
          'examples': [
            {
              'text': 'I ate an apple.',
              'translation': '我吃了一顆蘋果。',
              'translation_ai': false,
              'level': 'A2',
              'sense_id': 10
            },
          ],
          'relations': [
            {
              'relation': 'synonyms',
              'word': 'pome',
              'lexeme_id': 50,
              'native': '梨果',
              'cefr': 'C2',
              'hide_by_default': true
            },
          ],
          'morphemes': [
            {'part': 'apple', 'kind': 'root', 'meaning': null, 'native': '蘋果'},
          ],
          'etymology': {'text': 'From Old English æppel.', 'native': '源自古英語'},
          'missing': {'audio': 'no clip'},
          'picture_ids': [1],
        },
        {
          'id': 2,
          'lemma': 'tore',
          'normalized': 'tore',
          'pos': 'verb',
          'status': 'full',
          'redirect_to': 3,
        },
        {
          'id': 3,
          'lemma': 'tear',
          'normalized': 'tear',
          'pos': 'verb',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 30, 'definition': 'To rip.', 'native': '撕裂'},
          ],
        },
        {
          'id': 50,
          'lemma': 'pome',
          'normalized': 'pome',
          'pos': 'noun',
          'status': 'stub'
        },
      ],
    };

void main() {
  late Directory dir;
  setUp(() => dir = Directory.systemTemp.createTempSync('card428_'));
  tearDown(() {
    LexiconPack.instance.clear();
    try {
      dir.deleteSync(recursive: true);
    } on FileSystemException {
      // Windows keeps a handle for a moment; the temp dir is cleaned later.
    }
  });

  String build(Map<String, dynamic> j, [String name = 'pack.sqlite']) {
    final path = '${dir.path}/$name';
    LexiconSqlite.build(j, path);
    return path;
  }

  test('a SQLite pack reads like the JSON pack it was built from', () {
    final fromJson = LexiconPack()..loadJson(pack());
    final fromDb = LexiconPack()..loadSqlite(build(pack()));
    expect(fromDb.fromSqlite, isTrue);
    expect(fromJson.fromSqlite, isFalse);
    for (final p in [fromJson, fromDb]) {
      expect(p.version, 'v1');
      expect(p.target, 'en');
      expect(p.native, 'zh-TW');
      expect(p.mediaBase, '/api/audio');
      expect(p.hasCatalog, isTrue);
      expect(p.catalogImages.single['id'], 7);
      expect(p.labels['pos:noun'], '名詞');
      expect(p.size, 2, reason: 'stubs are not words');
      expect(p.byId(99)!.lemma, 'apple', reason: 'redirects table');
      expect(p.byId(2)!.lemma, 'tear', reason: 'pointer row redirects');
      expect(p.lookup('tore')!.entry.lemma, 'tear');
      final apple = p.lookup('apples', pos: 'noun')!;
      expect(apple.via, 'form');
      final e = apple.entry;
      expect(e.cefr, 'A1');
      expect(e.zipf, 4.8);
      expect(e.pictureIds, [1]);
      expect(e.learnerMeaning, '蘋果');
      expect(e.senses.single.register, 'spoken');
      expect(e.ipa, '/ˈæp.əl/');
      expect(e.audio, 'audio/en/abc.mp3');
      expect(e.audioCredit, 'CC BY-SA 4.0');
      expect(e.recordings.single.path, 'audio/en/abc.mp3');
      expect(e.examples.single.translation, '我吃了一顆蘋果。');
      expect(e.examples.single.senseId, 10);
      expect(e.relations.single.hideByDefault, isTrue);
      expect(e.morphemes.single.native, '蘋果');
      expect(e.etymology!.native, '源自古英語');
      expect(e.missing, {'audio': 'no clip'});
      expect(e.breakdown, 'apple');
      final detail = p.detail('apple')!;
      expect(detail.ipa, '/ˈæp.əl/');
      expect(detail.exampleSentences.single.zh, '我吃了一顆蘋果。');
      expect(detail.synonyms, ['pome']);
      expect(detail.etymology, '源自古英語');
      expect(p.usagesFor('apple').single.senses.single.meaning, '蘋果');
      expect(p.entriesFor('tear').single.learnerMeaning, '撕裂');
      expect(p.lookup('tear')!.entry.examples, isEmpty,
          reason: 'a row without a body has empty detail');
    }
    fromDb.clear();
  });

  test('replaceWith hands the SQLite pack over with its lazy entries', () {
    final candidate = LexiconPack()..loadSqlite(build(pack()));
    final apple = candidate.lookup('apple')!.entry;
    LexiconPack.instance.replaceWith(candidate);
    expect(candidate.fromSqlite, isFalse);
    expect(LexiconPack.instance.fromSqlite, isTrue);
    expect(identical(LexiconPack.instance.lookup('apple')!.entry, apple),
        isTrue);
    // Read after the hand-over: the file is still open.
    expect(apple.examples.single.text, 'I ate an apple.');
    expect(LexiconPack.instance.lookup('apple')!.entry.relations, hasLength(1));
  });

  test('a delta patches the SQLite file and re-indexes it', () {
    final path = build(pack());
    final p = LexiconPack()..loadSqlite(path);
    final next = pack(version: 'v2', meaning: '蘋果（更新）');
    (next['lexemes'] as List).removeWhere((r) => r['id'] == 50);
    (next['lexemes'] as List).add({
      'id': 60,
      'lemma': 'pear',
      'normalized': 'pear',
      'pos': 'noun',
      'status': 'full',
      'senses': [
        {'id': 61, 'definition': 'A fruit.', 'native': '梨'}
      ],
    });
    final base = pack();
    final before = {
      for (final r in base['lexemes'] as List) r['id']: jsonEncode(r)
    };
    final patch = {
      'delta_version': 1,
      'base_version': 'v1',
      'metadata': {
        for (final e in next.entries)
          if (e.key != 'lexemes') e.key: e.value
      },
      'order': [for (final r in next['lexemes'] as List) r['id']],
      'upserts': [
        for (final r in next['lexemes'] as List)
          if (before[r['id']] != jsonEncode(r)) r
      ],
    };
    expect((patch['upserts'] as List).map((r) => r['id']), [1, 60]);
    p.applySqliteDelta(patch);
    expect(p.version, 'v2');
    expect(p.lookup('apple')!.entry.learnerMeaning, '蘋果（更新）');
    expect(p.lookup('pear')!.entry.learnerMeaning, '梨');
    expect(p.byId(50), isNull);
    expect(p.lookup('tear')!.entry.cefr, 'B1', reason: 'untouched rows stay');
    // The file itself changed: a fresh open sees v2 in the new order.
    p.clear();
    final again = LexiconPack()..loadSqlite(path);
    expect(again.version, 'v2');
    expect(again.catalogWords.map((e) => e.id), [1, 3, 60]);
    again.clear();

    // A patch for another base version leaves the file alone.
    final stale = LexiconPack()..loadSqlite(path);
    expect(() => stale.applySqliteDelta({...patch, 'base_version': 'v0'}),
        throwsFormatException);
    expect(stale.version, 'v2');
    stale.clear();
  });

  test('inspect reads a pack\'s language pair and version cheaply', () {
    final path = build(pack());
    final info = LexiconSqlite.inspect(path)!;
    expect((info.target, info.native, info.version), ('en', 'zh-TW', 'v1'));
    expect(LexiconSqlite.inspect('${dir.path}/missing.sqlite'), isNull);
    File('${dir.path}/junk.sqlite').writeAsStringSync('not a database');
    expect(LexiconSqlite.inspect('${dir.path}/junk.sqlite'), isNull);
  });

  test('load() copies the bundled SQLite pack once per version', () async {
    LexiconPack.storageDirectory = () async => Directory('${dir.path}/store');
    final bundle = _Bundle({
      LexiconPack.manifestAssetFor('en', 'zh-TW'):
          utf8.encode(jsonEncode({'created_at': 'v1'})),
      LexiconPack.sqliteAssetFor('en', 'zh-TW'):
          File(build(pack(), 'asset.sqlite')).readAsBytesSync(),
    });
    final p = LexiconPack();
    await p.load(target: 'en', native: 'zh-TW', bundle: bundle);
    expect(p.fromSqlite, isTrue);
    expect(p.lookup('apple')!.entry.learnerMeaning, '蘋果');
    final copied = LexiconPack.bundledSqlitePath(
        Directory('${dir.path}/store'), 'en', 'zh-TW');
    expect(File(copied).existsSync(), isTrue);
    expect(bundle.loads, 1);
    p.clear();

    // Same version: the copy is reused, the asset is not read again.
    final q = LexiconPack();
    await q.load(target: 'en', native: 'zh-TW', bundle: bundle);
    expect(q.lookup('apple'), isNotNull);
    expect(bundle.loads, 1);
    q.clear();

    // A new bundled version replaces the copy.
    bundle.assets[LexiconPack.manifestAssetFor('en', 'zh-TW')] =
        utf8.encode(jsonEncode({'created_at': 'v2'}));
    bundle.assets[LexiconPack.sqliteAssetFor('en', 'zh-TW')] =
        File(build(pack(version: 'v2', meaning: '蘋果二'), 'asset2.sqlite'))
            .readAsBytesSync();
    final r = LexiconPack();
    await r.load(target: 'en', native: 'zh-TW', bundle: bundle);
    expect(r.version, 'v2');
    expect(r.lookup('apple')!.entry.learnerMeaning, '蘋果二');
    expect(bundle.loads, 2);
    r.clear();
  });

  test('without a SQLite asset load() falls back to the JSON pack', () async {
    LexiconPack.storageDirectory = () async => Directory('${dir.path}/store');
    final bundle = _Bundle({
      LexiconPack.assetFor('en', 'zh-TW'): utf8.encode(jsonEncode(pack())),
    });
    final p = LexiconPack();
    await p.load(target: 'en', native: 'zh-TW', bundle: bundle);
    expect(p.fromSqlite, isFalse);
    expect(p.lookup('apple')!.entry.learnerMeaning, '蘋果');
  });

  test('the Python builder and the Dart reader agree (pack_sqlite.py)',
      () async {
    final json = File('${dir.path}/pack.json')
      ..writeAsStringSync(jsonEncode(pack()));
    final out = '${dir.path}/py.sqlite';
    final ProcessResult result;
    try {
      result = await Process.run(
          'python', ['-I', '../pack_sqlite.py', json.path, out]);
    } on ProcessException {
      markTestSkipped('python not installed');
      return;
    }
    expect(result.exitCode, 0, reason: '${result.stdout}${result.stderr}');
    final p = LexiconPack()..loadSqlite(out);
    expect(p.version, 'v1');
    expect(p.catalogImages.single['id'], 7);
    final apple = p.lookup('apple')!.entry;
    expect(apple.learnerMeaning, '蘋果');
    expect(apple.examples.single.translation, '我吃了一顆蘋果。');
    expect(apple.etymology!.native, '源自古英語');
    expect(apple.missing, {'audio': 'no clip'});
    expect(p.lookup('tore')!.entry.lemma, 'tear');
    expect(p.lookup('tear')!.entry.examples, isEmpty);
    p.clear();
  });
}

/// An asset bundle with the given files (no caching, so a test can swap
/// the bundled version); counts [load]s of binary assets.
class _Bundle extends AssetBundle {
  _Bundle(this.assets);
  final Map<String, List<int>> assets;
  int loads = 0;

  @override
  Future<ByteData> load(String key) async {
    final data = assets[key];
    if (data == null) throw FlutterError('Missing asset $key');
    if (!key.endsWith('.json')) loads++;
    return ByteData.sublistView(Uint8List.fromList(data));
  }

  @override
  Future<T> loadStructuredData<T>(
          String key, Future<T> Function(String value) parser) async =>
      parser(await loadString(key));
}
