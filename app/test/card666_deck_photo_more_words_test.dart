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

// 問題回報 #666: on a picture downloaded from a 卡片集 (水果與蔬菜圖片集),
// 「多看動詞」「難一點」 seemed to do nothing. The deck's labels are all nouns
// already on the list, the list kept its words, and nothing told the learner
// whether 照片辨識 was asked. Now the tap brings verbs in — asking the
// recognizer for them, deck pictures too — or says there are none.

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

Map<String, Object> _verbs(List<String> words) => {
      'candidates': [
        for (final (i, w) in words.indexed)
          {
            'word': w,
            'pos': 'verb',
            'meaning': '$w 義',
            'cefr': 'A1',
            'point': [0.2 + i * 0.2, 0.6],
          },
      ],
    };

Future<String> _addDeckPicture(WidgetTester tester, PhotoIntake intake) async {
  final saved = await tester.runAsync(() => intake.addDeckPicture(
      Uint8List.fromList(_png),
      title: '水果',
      labels: _deckLabels()));
  return saved!.photo.id;
}

void main() {
  group('PhotoWordSession on a deck picture', () {
    late WordDatabaseRepository repo;
    late TaggingQueue queue;
    late List<http.Request> seen;
    late List<String> reply;

    TaggingQueue queueFor(AppSettings settings) {
      final intake = PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((r) async {
            seen.add(r);
            return jsonResponse(_verbs(reply));
          }),
        ),
      );
      return TaggingQueue(
          repository: () => repo,
          settings: settings,
          intake: intake,
          lexicon: testLexicon);
    }

    setUp(() {
      repo = _repo();
      seen = [];
      reply = ['peel', 'wash'];
    });

    testWidgets('多看動詞 asks the recognizer and the verbs join the list',
        (tester) async {
      queue = queueFor(AppSettings.inMemory(
          taggingUrl: 'http://127.0.0.1:8765/tag', apiKey: 'k'));
      final id = await _addDeckPicture(tester, queue.intake);
      expect(id, startsWith('photo-deck-'));
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      expect(s.words.map((w) => w.word), _fruits);

      s.setBias(PosBias.actions);
      expect(s.fetchingMore, 'actions', reason: 'shows it is looking');
      await tester.runAsync(() async {
        for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      expect(seen.single.url.queryParameters['focus'], 'actions');
      expect(seen.single.url.queryParameters['exclude'], contains('apple'));
      expect(s.fetchingMore, isNull);
      expect(s.words.map((w) => w.word), containsAll(['peel', 'wash']));
      expect(s.words.length, WordSelector.maxWords);
      expect(notices, isEmpty);
      s.dispose();
    });

    testWidgets('no new verb → says so instead of doing nothing',
        (tester) async {
      reply = [];
      queue = queueFor(
          AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'));
      final id = await _addDeckPicture(tester, queue.intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      s.setBias(PosBias.actions);
      await tester.runAsync(() async {
        for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      expect(seen, hasLength(1));
      expect(notices.single, contains('沒有更多動詞'));

      // 問題回報 #671: every tap scans the photo again.
      s.setBias(PosBias.actions); // off
      s.setBias(PosBias.actions); // on
      await tester.runAsync(() async {
        for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      expect(seen, hasLength(2));
      expect(notices.last, contains('沒有更多動詞'));
      s.dispose();
    });

    testWidgets('no recognizer → tells the learner how to get more',
        (tester) async {
      queue = queueFor(AppSettings.inMemory());
      final id = await _addDeckPicture(tester, queue.intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      s.setBias(PosBias.actions);
      expect(notices.single, contains('連上照片辨識'));
      s.setTarget(s.target + 1);
      expect(notices.last, contains('沒有更多更難的字'));
      expect(seen, isEmpty);
      s.dispose();
    });

    testWidgets('難一點 with nothing harder asks for harder words',
        (tester) async {
      reply = [];
      queue = queueFor(
          AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'));
      final id = await _addDeckPicture(tester, queue.intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      s.setTarget(s.target + 1);
      await tester.runAsync(() async {
        for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      expect(seen.single.url.queryParameters['focus'], 'harder');
      expect(notices.single, contains('沒有更多更難的字'));
      s.dispose();
    });

    testWidgets('offline → can be tried again', (tester) async {
      var online = false;
      final intake = PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((r) async {
            if (!online) throw http.ClientException('Connection refused');
            seen.add(r);
            return jsonResponse(_verbs(reply));
          }),
        ),
      );
      queue = TaggingQueue(
          repository: () => repo,
          settings:
              AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'),
          intake: intake,
          lexicon: testLexicon);
      final id = await _addDeckPicture(tester, intake);
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      final notices = <String>[];
      s.onNotice = notices.add;
      Future<void> wait() => tester.runAsync(() async {
            for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
              await Future<void>.delayed(const Duration(milliseconds: 10));
            }
          });
      s.setBias(PosBias.actions);
      await wait();
      expect(notices.single, contains('連不到照片辨識'));

      online = true;
      s.setBias(PosBias.actions); // off
      s.setBias(PosBias.actions); // on again
      await wait();
      expect(s.words.map((w) => w.word), contains('peel'));
      s.dispose();
    });
  });

  group('照片詳情 (widget)', () {
    testWidgets('tapping 多看動詞 shows the new verbs on the list', (tester) async {
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
                return jsonResponse(_verbs(['peel']));
              })),
          size: const Size(390, 844));
      final id = await _addDeckPicture(tester, app.queue.intake);
      app.navigator.openPhoto(id);
      await tester.pumpAndSettle();
      expect(find.text('Peel'), findsNothing);

      final pill = find.textContaining('多看動詞');
      await tester.ensureVisible(pill);
      await tester.tap(pill);
      await tester.pump();
      expect(find.textContaining('AI 正在找更多動詞'), findsOneWidget);
      await settle(tester,
          until: () => find.text('Peel').evaluate().isNotEmpty);
      expect(find.text('Peel'), findsWidgets);
      expect(find.textContaining('AI 正在找更多動詞'), findsNothing);
    });

    testWidgets('no new verb → a snack bar says so', (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.album,
          repository: _repo(),
          settings:
              AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'),
          createTagger: (uri, key) => TaggingService(
              endpoint: uri,
              apiKey: key,
              client: MockClient((r) async => jsonResponse(_verbs([])))),
          size: const Size(390, 844));
      final id = await _addDeckPicture(tester, app.queue.intake);
      app.navigator.openPhoto(id);
      await tester.pumpAndSettle();

      final pill = find.textContaining('多看動詞');
      await tester.ensureVisible(pill);
      await tester.tap(pill);
      await settle(tester,
          until: () => find.textContaining('沒有更多動詞').evaluate().isNotEmpty);
      expect(find.textContaining('這張照片沒有更多動詞了'), findsOneWidget);
    });
  });
}
