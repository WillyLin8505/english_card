import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

// 問題回報 #670: 照片詳情要一個「重新掃描標籤」按鈕。
// 問題回報 #671: 按「多看動詞」（難一點…）時每次都要重新掃描這張照片，
// 給出新的動詞，而不是只在列表沒變時才問一次。

final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAEElEQVR4nGNocFCAIwacHADRZwqBZaYHGAAAAABJRU5ErkJggg==');

const _fruits = ['apple', 'banana', 'carrot', 'tomato', 'grape'];

List<WordCandidate> _deckLabels() => [
      for (final (i, w) in _fruits.indexed)
        WordCandidate(
          word: w,
          pos: 'noun',
          meaning: '$w 義',
          level: 'A1',
          levelSource: 'cefr-j',
          evidence: 'deck',
          point: LabelPoint(0.1 + i * 0.18, 0.4),
          visualConfidence: 0.9,
          usefulness: 0.8,
        ),
    ];

WordDatabaseRepository _repo() => WordDatabaseRepository(
    clock: () => testNow,
    profile: UserVocabularyProfile.start('A1', now: testNow));

Map<String, Object> _reply(List<(String, String)> words) => {
      'candidates': [
        for (final (i, (w, pos)) in words.indexed)
          {
            'word': w,
            'pos': pos,
            'meaning': '$w 義',
            'cefr': 'A1',
            'point': [0.2 + i * 0.15, 0.6],
          },
      ],
    };

void main() {
  late WordDatabaseRepository repo;
  late List<http.Request> seen;
  late List<List<(String, String)>> replies;

  PhotoIntake intakeFor() => PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((r) async {
            seen.add(r);
            final next =
                replies.isEmpty ? <(String, String)>[] : replies.removeAt(0);
            return jsonResponse(_reply(next));
          }),
        ),
      );

  TaggingQueue queueFor(PhotoIntake intake, {bool configured = true}) =>
      TaggingQueue(
          repository: () => repo,
          settings: configured
              ? AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k')
              : AppSettings.inMemory(),
          intake: intake,
          lexicon: testLexicon);

  Future<String> deckPicture(WidgetTester tester, PhotoIntake intake) async {
    final saved = await tester.runAsync(() => intake.addDeckPicture(
        Uint8List.fromList(_png),
        title: '水果',
        labels: _deckLabels()));
    return saved!.photo.id;
  }

  Future<void> idle(WidgetTester tester, PhotoWordSession s) =>
      tester.runAsync(() async {
        for (var i = 0;
            i < 100 && (s.fetchingMore != null || s.rescanning);
            i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });

  setUp(() {
    repo = _repo();
    seen = [];
    replies = [];
  });

  group('#671 多看動詞 asks every time', () {
    testWidgets('two taps → two focus=actions requests, new verbs swapped in',
        (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      replies = [
        [('peel', 'verb'), ('wash', 'verb')],
        [('slice', 'verb'), ('squeeze', 'verb')],
      ];

      s.setBias(PosBias.actions);
      await idle(tester, s);
      expect(s.words.map((w) => w.word), containsAll(['peel', 'wash']));

      s.setBias(PosBias.actions); // off
      s.setBias(PosBias.actions); // on again: scans again
      await idle(tester, s);
      expect(seen, hasLength(2));
      expect(seen.map((r) => r.url.queryParameters['focus']),
          everyElement('actions'));
      expect(seen.last.url.queryParameters['exclude'], contains('peel'));
      final shown = s.words.map((w) => w.word).toList();
      expect(shown, containsAll(['slice', 'squeeze']));
      expect(shown.length, WordSelector.maxWords);
      expect(s.words.where((w) => w.candidate.isAction).length,
          greaterThanOrEqualTo(WordSelector.biasWords));
      expect(notices, isEmpty);
      s.dispose();
    });

    testWidgets('a tap while the same request runs does not send it twice',
        (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      replies = [
        [('peel', 'verb'), ('wash', 'verb')],
      ];
      s.setBias(PosBias.actions);
      s.setBias(PosBias.actions); // off
      s.setBias(PosBias.actions); // on, still fetching
      await idle(tester, s);
      expect(seen, hasLength(1));
      expect(s.words.map((w) => w.word), containsAll(['peel', 'wash']));
      s.dispose();
    });

    testWidgets('難一點 twice → two focus=harder requests', (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      s.setTarget(s.target + 1);
      await idle(tester, s);
      s.setTarget(s.target - 1);
      await idle(tester, s);
      s.setTarget(s.target + 1);
      await idle(tester, s);
      expect(
          seen
              .where((r) => r.url.queryParameters['focus'] == 'harder')
              .length,
          2);
      s.dispose();
    });
  });

  group('#670 重新掃描標籤', () {
    testWidgets('scans without focus; new words show, the learner\'s stay',
        (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      s.add(word: 'knife', meaning: '刀');
      final starred = s.words.firstWhere((w) => w.word == 'apple');
      s.toggleStar(starred);
      replies = [
        [('bowl', 'noun'), ('peel', 'verb')],
      ];

      final done = s.rescan();
      expect(s.rescanning, isTrue);
      await tester.runAsync(() => done);
      expect(s.rescanning, isFalse);
      final r = seen.single;
      expect(r.url.queryParameters.containsKey('focus'), isFalse);
      final shown = s.words.map((w) => w.word).toList();
      expect(shown, containsAll(['bowl', 'peel', 'knife', 'apple']));
      expect(repo.photo(id)!.candidates.map((c) => c.word),
          containsAll([..._fruits, 'bowl', 'peel']));
      expect(notices.single, contains('新增了 2 個'));
      s.dispose();
    });

    testWidgets('nothing new → says so', (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      final before = s.words.map((w) => w.word).toList();
      await tester.runAsync(s.rescan);
      expect(seen, hasLength(1));
      expect(s.words.map((w) => w.word), before);
      expect(notices.single, contains('沒有新的'));
      s.dispose();
    });

    testWidgets('no recognizer → points to 設定', (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake, configured: false);
      final id = await deckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      await tester.runAsync(s.rescan);
      expect(seen, isEmpty);
      expect(notices.single, contains('設定'));
      s.dispose();
    });

    testWidgets('works on a photo the learner took', (tester) async {
      final intake = intakeFor();
      final queue = queueFor(intake);
      replies = [
        [('cup', 'noun'), ('table', 'noun')],
        [('spoon', 'noun')],
      ];
      final photo = await tester.runAsync(
          () => intake.addPhoto(Uint8List.fromList(_png), title: '桌上'));
      await tester.runAsync(queue.process);
      final s = PhotoWordSession(repo: repo, photoId: photo!.id, queue: queue);
      expect(s.words.map((w) => w.word), containsAll(['cup', 'table']));
      await tester.runAsync(s.rescan);
      expect(seen, hasLength(2));
      expect(seen.last.url.queryParameters.containsKey('focus'), isFalse);
      expect(s.words.map((w) => w.word),
          containsAll(['cup', 'table', 'spoon']));
      s.dispose();
    });
  });

  testWidgets('照片詳情: 重新掃描標籤 shows progress, then the new word',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        repository: _repo(),
        settings: AppSettings.inMemory(
            taggingUrl: 'http://127.0.0.1:8765/tag', apiKey: 'k'),
        createTagger: (uri, key) => TaggingService(
            endpoint: uri,
            apiKey: key,
            client: MockClient((r) async {
              await Future<void>.delayed(const Duration(milliseconds: 50));
              return jsonResponse(_reply([('peel', 'verb')]));
            })),
        size: const Size(390, 844));
    final saved = await tester.runAsync(() => app.queue.intake.addDeckPicture(
        Uint8List.fromList(_png),
        title: '水果',
        labels: _deckLabels()));
    app.navigator.openPhoto(saved!.photo.id);
    await tester.pumpAndSettle();
    expect(find.text('Peel'), findsNothing);

    final button = find.text('重新掃描標籤');
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
    expect(find.textContaining('AI 正在重新掃描'), findsOneWidget);
    await settle(tester,
        until: () => find.textContaining('新增了').evaluate().isNotEmpty);
    expect(find.text('Peel'), findsWidgets);
    expect(find.textContaining('新增了 1 個單字'), findsOneWidget);
    expect(find.textContaining('AI 正在重新掃描'), findsNothing);
  });
}
