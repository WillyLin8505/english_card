import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/local_vision.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 問題回報 #265 (owner decision 2026-10-18): the store build recognizes
// photos on the phone and ships its dictionary; no server address or key.
void main() {
  tearDown(() {
    LocalVision.classifier = null;
    AppSettings.localRecognition = false;
  });

  test('classifier labels become known words, best first, spread out', () {
    final cs = candidatesFromLabels(
      [
        (label: 'golden_retriever', confidence: 0.95),
        (label: 'dog', confidence: 0.9),
        (label: 'grass', confidence: 0.6),
        (label: 'outdoor', confidence: 0.05),
        (label: 'zzqx', confidence: 0.8),
      ],
      lexicon: testLexicon(),
      level: 'A1',
      pack: LexiconPack(),
    );
    final words = cs.map((c) => c.word).toList();
    expect(words.first, 'dog');
    expect(words, contains('grass'));
    expect(words, isNot(contains('zzqx'))); // nobody knows it
    expect(words, isNot(contains('outdoor'))); // below the confidence floor
    expect(cs.first.visualConfidence, 0.9);
    expect(cs.every((c) => c.evidence.isNotEmpty), isTrue);
    // No positions from the classifier: labels fan out instead of piling up.
    expect({for (final c in cs) '${c.point.x},${c.point.y}'}.length, cs.length);
  });

  test('a learner-level word outranks a harder one at equal confidence', () {
    final cs = candidatesFromLabels(
      [
        (label: 'apple', confidence: 0.8),
        (label: 'orchard', confidence: 0.8),
      ],
      lexicon: testLexicon(),
      level: 'A1',
      pack: LexiconPack(),
    );
    expect(cs.map((c) => c.word).first, 'apple');
  });

  test('without a server address the queue tags on the device', () async {
    AppSettings.localRecognition = true;
    LocalVision.classifier = (bytes, max) async => [
          (label: 'apple', confidence: 0.9),
          (label: 'table', confidence: 0.7),
        ];
    final repo = WordDatabaseRepository(clock: () => testNow);
    final store = PhotoStore.inMemory();
    var remoteCalls = 0;
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: store,
      createTagger: (uri, key) {
        remoteCalls++;
        throw StateError('no server in the store build');
      },
    );
    final saved = await store.save('p1', Uint8List.fromList('photo'.codeUnits));
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'p1',
        takenAt: testNow,
        storedKey: saved.storedKey,
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending));
    final settings = AppSettings.inMemory();
    expect(settings.usesLocalRecognition, isTrue);
    expect(settings.taggingConfigured, isTrue);
    expect(settings.showsTaggingServer, isFalse);

    final queue = TaggingQueue(
        repository: () => repo,
        settings: settings,
        intake: intake,
        lexicon: testLexicon);
    await queue.process();

    final p = repo.photo('p1')!;
    expect(p.taggingStatus, TaggingStatus.done);
    expect(p.candidates.map((c) => c.word), containsAll(['apple', 'table']));
    expect(remoteCalls, 0);
  });

  test('a server address still wins over the device (developer build)', () {
    AppSettings.localRecognition = true;
    final s = AppSettings.inMemory(taggingUrl: 'http://x/tag');
    expect(s.usesLocalRecognition, isFalse);
    expect(s.showsTaggingServer, isTrue);
    expect(s.taggingConfigured, isTrue);
  });

  test('a platform failure shows a plain sentence, not the English error',
      () async {
    // 問題回報 #370: the simulator's Vision fails with "Failed to create
    // espresso context." — that text must not reach the learner.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(LocalVision.channel, (call) async {
      throw PlatformException(
          code: 'vision', message: 'Failed to create espresso context.');
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(LocalVision.channel, null));
    await expectLater(
      LocalVision.classify(Uint8List.fromList([1, 2, 3])),
      throwsA(isA<TaggingApiException>().having(
          (e) => e.message, 'message', visionFailedMessage)),
    );
    expect(visionFailedMessage, isNot(contains('espresso')));
    expect(visionFailedMessage, isNot(matches(RegExp(r'[A-Za-z]{4,}'))));
  });

  test('a device that cannot classify has no recognition', () {
    final s = AppSettings.inMemory();
    expect(s.usesLocalRecognition, isFalse);
    expect(s.taggingConfigured, isFalse);
    expect(s.showsTaggingServer, isFalse);
  });

  testWidgets('設定 shows no address or key on the phone', (tester) async {
    AppSettings.localRecognition = true;
    await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 2400));
    expect(find.text('照片在這支手機上辨識，不會上傳到任何伺服器。'), findsOneWidget);
    expect(find.text('服務網址'), findsNothing);
    expect(find.text('連線金鑰（API Key）'), findsNothing);
    expect(find.textContaining('Ollama'), findsNothing);
  });

  test('the bundled pack is complete enough to ship', () {
    // lexicon/tools/card268_bundle_pack.py output: words, meanings, IPA and
    // pictures all live in the app; recordings only where bundled.
    final raw = File('assets/lexicon/en-zh-TW.json').readAsStringSync();
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final pack = LexiconPack()..loadJson(json);
    expect(json['bundled'], isTrue);
    expect(json['media_base'], isNull);
    expect(pack.size, greaterThan(4500));
    expect(pack.hasCatalog, isTrue);
    expect(pack.catalogImages.length, greaterThan(1500));
    expect(
        pack.catalogImages
            .every((i) => (i['url'] as String).startsWith('assets/lexicon/')),
        isTrue);
    final apple = pack.lookup('apple', pos: 'noun')!.entry;
    expect(apple.learnerMeaning, isNotNull);
    expect(apple.ipa, isNotNull);
    expect(apple.examples, isNotEmpty);
    expect(pack.detail('apple')!.synonyms, isNotNull);
    final recorded = <String>[];
    for (final e in [pack.lookup('go')?.entry, pack.lookup('dog')?.entry]) {
      if (e?.audio != null) recorded.add(e!.audio!);
    }
    for (final a in recorded) {
      expect(File('assets/lexicon/media/$a').existsSync(), isTrue, reason: a);
    }
  });

  test('with remote off nothing is polled or sent', () async {
    // flutter_test_config.dart switches the default off for tests.
    final s = DictionarySync();
    expect(s.remote, isFalse);
    expect(await s.sendMissing(), 0);
    s.dispose();
  });
}
