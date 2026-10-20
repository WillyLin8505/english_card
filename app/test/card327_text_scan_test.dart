import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/local_vision.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/text_scan.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

import 'helpers.dart';

// 問題回報 #324: words printed on a photo (signs, menus, book pages) become
// vocabulary candidates, read on the phone.
TextLine line(String text, double top, {double height = 0.05}) =>
    TextLine(text, LabelBox(0.1, top, 0.8, height), confidence: 0.9);

LexiconPack? _bundled;
LexiconPack bundledPack() => _bundled ??= LexiconPack()
  ..loadJson(jsonDecode(File('assets/lexicon/en-zh-TW.json').readAsStringSync())
      as Map<String, dynamic>);

void main() {
  tearDown(() {
    TextScan.recognizer = null;
    TextScan.available = false;
    LocalVision.classifier = null;
    AppSettings.localRecognition = false;
  });

  group('dictionary forms', () {
    String? lemma(String w, {LexiconPack? pack}) =>
        textLemma(w, lexicon: testLexicon(), pack: pack ?? LexiconPack())
            ?.lemma;

    test('inflections go back to the word, function words and names go', () {
      expect(lemma('menus'), 'menu');
      expect(lemma('Served'), 'serve');
      expect(lemma('cookies'), 'cookie');
      expect(lemma('children'), 'child');
      expect(lemma("chef's"), 'chef');
      expect(lemma('the'), isNull);
      expect(lemma('would'), isNull);
      expect(lemma('2024'), isNull);
      expect(lemma('x'), isNull);
      expect(lemma('Starbucks'), isNull); // a brand, in no dictionary
    });

    test('the language pack forms table is used first (tore → tear)', () {
      final pack = bundledPack();
      expect(lemma('apples', pack: pack), 'apple');
      final hit = textLemma('apples', lexicon: testLexicon(), pack: pack)!;
      expect(hit.entry, isNotNull);
    });

    test('every inflected form in the bundled pack finds its word', () {
      // Whole-dictionary check: each listed form of a full entry must lead
      // back to a word of the pack (not necessarily the same one: "left"
      // is both leave's form and a word of its own).
      final pack = bundledPack();
      final raw =
          jsonDecode(File('assets/lexicon/en-zh-TW.json').readAsStringSync())
              as Map<String, dynamic>;
      var forms = 0, found = 0;
      final missed = <String>[];
      for (final e in (raw['lexemes'] as List)) {
        if (e is! Map || e['redirect_to'] != null) continue;
        for (final f in (e['forms'] as List? ?? const [])) {
          final form = (f is Map ? f['form'] ?? f['normalized'] : f) as String?;
          if (form == null || !RegExp(r'^[a-z]+$').hasMatch(form)) continue;
          if (textStopWords.contains(form)) continue;
          forms++;
          if (textLemma(form, lexicon: testLexicon(), pack: pack) != null) {
            found++;
          } else if (missed.length < 10) {
            missed.add(form);
          }
        }
      }
      expect(forms, greaterThan(1000));
      expect(found / forms, greaterThan(0.97), reason: 'missed: $missed');
    });
  });

  test('a menu becomes framed words around the learner level', () {
    final cs = candidatesFromText(
      [
        line('TODAY\'S SPECIALS', 0.05, height: 0.1),
        line('Grilled salmon served with roasted vegetables', 0.3),
        line('Fresh orange juice', 0.4),
        line('Please ask Mark for the wine list', 0.5),
        line('Call 555-0199 · www.example.com', 0.6),
      ],
      lexicon: testLexicon(),
      level: 'B1',
      pack: LexiconPack(),
    );
    final words = cs.map((c) => c.word).toList();
    expect(words, containsAll(['salmon', 'serve', 'roast']));
    expect(words, isNot(contains('vegetable'))); // A1: a B1 learner knows it
    expect(words, isNot(contains('mark'))); // a name in running text
    expect(words, isNot(contains('the')));
    expect(words, isNot(contains('with')));
    expect(words, isNot(contains('www')));
    expect(words.toSet().length, words.length);
    for (final c in cs) {
      expect(c.box, isNotNull);
      expect(c.box!.contains(c.point), isTrue);
      expect(c.evidence, startsWith('照片文字'));
      expect(c.visualConfidence, greaterThanOrEqualTo(0.5));
    }
    // "served" sits in its line's box, after "Grilled salmon ".
    final serve = cs.firstWhere((c) => c.word == 'serve');
    expect(serve.box!.top, 0.3);
    expect(serve.box!.left, greaterThan(0.1 + 0.8 * 14 / 45));
  });

  test('words far below the learner are left out', () {
    final lines = [line('Open the door and read a good book', 0.2)];
    List<String> at(String level) => candidatesFromText(lines,
            lexicon: testLexicon(), level: level, pack: LexiconPack())
        .map((c) => c.word)
        .toList();
    expect(at('A1'), containsAll(['open', 'door', 'read', 'book']));
    expect(at('B2'), isEmpty);
  });

  test('a title-case sign keeps its words; a name-word mid-sentence goes', () {
    expect(looksLikeName(['Rose', 'Garden', 'Entrance'], 0), isFalse);
    expect(looksLikeName(['Fresh', 'Rose', 'Garden'], 1), isFalse);
    expect(looksLikeName(['ask', 'Rose', 'for', 'help'], 1), isTrue);
    expect(looksLikeName(['a', 'rose', 'for', 'you'], 1), isFalse);
  });

  test('the recognizer\'s word boxes win over splitting the line', () {
    final l = TextLine.fromMap({
      'text': 'Exit only',
      'confidence': 0.8,
      'box': [0.2, 0.4, 0.5, 0.1],
      'words': [
        {
          'text': 'Exit',
          'box': [0.2, 0.4, 0.2, 0.1]
        },
        {
          'text': 'only',
          'box': [0.45, 0.4, 0.25, 0.1]
        },
      ],
    })!;
    final ws = wordsOf(l);
    expect(ws.map((w) => w.text), ['Exit', 'only']);
    expect(ws.first.box.width, 0.2);
    expect(TextLine.fromMap({'text': 'no box'}), isNull);
    final split = wordsOf(const TextLine('ab cd', LabelBox(0, 0, 1, 0.1)));
    expect(split.last.box.left, closeTo(0.6, 1e-9));
  });

  test('a word candidate keeps its box and a photo its mode', () {
    const c = WordCandidate(
        word: 'exit',
        pos: 'noun',
        meaning: '出口',
        level: 'A2',
        levelSource: 'cefr-j',
        point: LabelPoint(0.3, 0.45),
        box: LabelBox(0.2, 0.4, 0.2, 0.1));
    final back = WordCandidate.fromJson(c.toJson());
    expect(back.box!.left, 0.2);
    expect(back.copyWith(meaning: '安全門').box, isNotNull);
    final p = Photo(
        id: 'p',
        title: 'p',
        takenAt: testNow,
        createdAt: testNow,
        scanMode: PhotoScanMode.both);
    expect(Photo.fromJson(p.toJson()).scanMode, PhotoScanMode.both);
    final old =
        Photo(id: 'q', title: 'q', takenAt: testNow, createdAt: testNow);
    expect(old.toJson().containsKey('scanMode'), isFalse);
    expect(Photo.fromJson(old.toJson()).scanMode, PhotoScanMode.objects);
  });

  Future<(WordDatabaseRepository, TaggingQueue)> queueWith(
      PhotoScanMode mode, AppSettings settings) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final store = PhotoStore.inMemory();
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: store,
      createTagger: (uri, key) => throw StateError('no server'),
    );
    final saved = await store.save('p1', Uint8List.fromList('photo'.codeUnits));
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'p1',
        takenAt: testNow,
        storedKey: saved.storedKey,
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending,
        scanMode: mode));
    return (
      repo,
      TaggingQueue(
          repository: () => repo,
          settings: settings,
          intake: intake,
          lexicon: testLexicon)
    );
  }

  test('找文字 works on a phone with no picture recognizer', () async {
    TextScan.available = true;
    TextScan.recognizer = (_) async => [line('Emergency exit', 0.2)];
    final settings = AppSettings.inMemory();
    expect(settings.taggingConfigured, isFalse);
    expect(settings.scanMode, PhotoScanMode.text);
    final (repo, queue) = await queueWith(PhotoScanMode.text, settings);
    await queue.process();
    final p = repo.photo('p1')!;
    expect(p.taggingStatus, TaggingStatus.done);
    expect(p.candidates.map((c) => c.word), contains('emergency'));
    expect(p.candidates.every((c) => c.box != null), isTrue);
    expect(queue.canTopUp(p, 'harder'), isFalse); // text is read once
  });

  test('兩者都找 merges things in the picture with printed words', () async {
    AppSettings.localRecognition = true;
    TextScan.available = true;
    LocalVision.classifier =
        (_, __) async => [(label: 'apple', confidence: 0.9)];
    TextScan.recognizer = (_) async => [line('Organic apples', 0.7)];
    final (repo, queue) =
        await queueWith(PhotoScanMode.both, AppSettings.inMemory());
    await queue.process();
    final words = repo.photo('p1')!.candidates.map((c) => c.word).toList();
    expect(words, containsAll(['apple', 'organic']));
    expect(words.where((w) => w == 'apple').length, 1);
  });

  test('找文字 on the web fails with an explanation, not forever pending',
      () async {
    TextScan.recognizer =
        (_) async => throw TaggingApiException(TextScan.unavailableMessage);
    final (repo, queue) =
        await queueWith(PhotoScanMode.text, AppSettings.inMemory());
    await queue.process();
    final p = repo.photo('p1')!;
    expect(p.taggingStatus, TaggingStatus.failed);
  });

  // 問題回報 #409: the dialog no longer asks 找什麼; it always looks for both.
  testWidgets('the save dialog does not ask 找什麼 and always finds both',
      (tester) async {
    for (final available in [true, false]) {
      TextScan.available = available;
      final repository = WordDatabaseRepository();
      repository.addAlbum(name: '旅行');
      SavePhotoChoice? result;
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => FilledButton(
            onPressed: () async => result = await showSaveToAlbumDialog(context,
                repository: repository, defaultTitle: '照片'),
            child: const Text('開啟'),
          ),
        ),
      ));
      await tester.tap(find.text('開啟'));
      await tester.pumpAndSettle();
      expect(find.text('找物品'), findsNothing);
      expect(find.text('找文字'), findsNothing);
      expect(find.text('兩者都找'), findsNothing);
      await tester.tap(find.text('儲存'));
      await tester.pumpAndSettle();
      expect(result!.scanMode, PhotoScanMode.both);
    }
    TextScan.available = true;
  });
}
