// 問題回報 #729: 「當我已經切換到第二張卡片的時候，上一張卡片的聲音就不要再
// 出來了」— a flip plays two accents in a row and each may first wait for a
// download, so the old card's second accent used to start after the swipe.
// 問題回報 #724: an accent with no recording says it is synthesized (合成).
// 問題回報 #726: the next cards (and their photos) are known ahead, so they
// are loaded while the current card is up.
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/audio_file_cache.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// Each say() waits until the test lets it finish, like a recording that
/// is still downloading.
class _SlowSpeaker implements Speaker {
  final said = <(String, String)>[];
  final pending = <Completer<bool>>[];
  var stops = 0;

  @override
  Future<bool> say(String text,
      {required String language, String? audioUrl, String accent = 'en-GB'}) {
    said.add((text, accent));
    final done = Completer<bool>();
    pending.add(done);
    return done.future;
  }

  @override
  Future<void> stop() async => stops++;

  void finishAll() {
    for (final c in pending) {
      if (!c.isCompleted) c.complete(true);
    }
  }
}

WordEntry _word(String word, {int? lexemeId}) => WordEntry(
    id: 'w-$word',
    word: word,
    pos: 'noun',
    meaning: '',
    lexemeId: lexemeId,
    createdAt: testNow,
    updatedAt: testNow);

void main() {
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('stopCardAudio ends a flip before its second accent',
      (tester) async {
    final speaker = _SlowSpeaker();
    await pumpApp(tester, initialTab: AppTab.settings, speaker: speaker);
    final context = tester.element(find.byType(Scaffold).first);

    final run = playBothAccents(context, _word('zebu'));
    await tester.pump();
    expect(speaker.said, [('zebu', 'en-GB')]);

    // The card changes while the British clip is still loading.
    stopCardAudio(speaker);
    expect(speaker.stops, 1);
    speaker.finishAll();
    await run;
    expect(speaker.said, [('zebu', 'en-GB')], reason: 'no American after');

    // A newer flip supersedes an older one the same way.
    speaker.said.clear();
    final first = playBothAccents(context, _word('yak'));
    await tester.pump();
    final second = playBothAccents(context, _word('gnu'));
    await tester.pump();
    speaker.finishAll();
    await first;
    await tester.pump();
    speaker.finishAll();
    await second;
    expect(speaker.said.where((s) => s.$1 == 'yak'), [('yak', 'en-GB')]);
    expect(speaker.said.where((s) => s.$1 == 'gnu'),
        [('gnu', 'en-GB'), ('gnu', 'en-US')]);
  });

  testWidgets('grading the card stops its sound; the next card is silent',
      (tester) async {
    final speaker = _SlowSpeaker();
    final app = await pumpApp(tester,
        initialTab: AppTab.review,
        speaker: speaker,
        repository: WordDatabaseRepository(clock: () => testNow));
    for (final (w, zh) in [('banana', '香蕉'), ('cherry', '櫻桃')]) {
      final word =
          app.repository.addWord(word: w, pos: 'n.', meaning: zh, level: 'A1');
      app.repository.applyWordData(word.id,
          newExamples: [
            WordExample(text: 'I ate a $w.', translation: '我吃了一個$zh。')
          ],
          status: WordDataStatus.complete);
    }
    await tester.pumpAndSettle();
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.space); // 顯示答案
    await tester.pumpAndSettle();
    expect(speaker.said, hasLength(1));
    final word = speaker.said.single.$1;
    final stopsBefore = speaker.stops;

    await tester.sendKeyEvent(LogicalKeyboardKey.digit3); // Good → next card
    await tester.pumpAndSettle();
    expect(speaker.stops, greaterThan(stopsBefore));

    // The old card's first clip finishes loading now: nothing follows it.
    speaker.finishAll();
    await tester.pumpAndSettle();
    expect(speaker.said, [(word, 'en-GB')]);

    // 上一張 also counts as a change of card.
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    final stopsOnNext = speaker.stops;
    await tester.tap(find.byKey(const ValueKey('previous-card')));
    await tester.pumpAndSettle();
    expect(speaker.stops, greaterThan(stopsOnNext));
    final heard = speaker.said.length;
    speaker.finishAll();
    await tester.pumpAndSettle();
    expect(speaker.said, hasLength(heard));

    // Leaving the review stops it too.
    final stopsBeforeLeaving = speaker.stops;
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(speaker.stops, greaterThan(stopsBeforeLeaving));
  });

  test('DeviceSpeaker: a clip still downloading when stopped never plays',
      () async {
    final tmp = Directory.systemTemp.createTempSync('review729_');
    addTearDown(() => tmp.deleteSync(recursive: true));
    final gate = Completer<void>();
    final played = <Source>[];
    final speaker = DeviceSpeaker(
        cache: AudioFileCache(
            directory: () async => Directory('${tmp.path}/audio'),
            download: (_) async {
              await gate.future;
              return [1, 2, 3];
            }),
        play: (source) async => played.add(source));
    final saying = speaker.say('eye',
        language: 'en', audioUrl: 'https://example.com/eye-US.mp3');
    await Future<void>.delayed(Duration.zero);
    await speaker.stop();
    gate.complete();
    expect(await saying, isTrue);
    expect(played, isEmpty);
  });

  group('問題回報 #724: any real recording before TTS, TTS marked 合成', () {
    setUp(() => LexiconPack.instance.loadJson({
          'schema_version': 3,
          'target_language': 'en',
          'native_language': 'zh-TW',
          'lexemes': [
            for (final (id, lemma, accent) in [
              (7, 'eye', 'US'),
              (8, 'owl', null), // a recording with no accent label
            ])
              {
                'id': id,
                'lemma': lemma,
                'normalized': lemma,
                'pos': 'noun',
                'pronunciations': [
                  {
                    'kind': 'audio',
                    'accent': accent,
                    'default': true,
                    'audio': 'audio/en/$lemma.mp3'
                  },
                ],
              },
            {'id': 9, 'lemma': 'zebu', 'normalized': 'zebu', 'pos': 'noun'},
          ],
        }));

    Future<void> pumpBack(WidgetTester tester, WordEntry entry) async {
      await pumpApp(tester,
          speaker: SilentSpeaker(),
          home: Scaffold(
              body: SingleChildScrollView(
                  child: FlashcardBack(
            entry: entry,
            card: LearningCard(
                id: 'card-${entry.word}',
                wordEntryId: entry.id,
                templateId: 'test'),
            photo: null,
            anchor: null,
            learnerLevel: 'A1',
            onPlay: () {},
            onOpen: () {},
            template: const CardTemplate(id: 'test', name: 'test', backFields: [
              TemplateField(CardBackField.pronunciation),
            ]),
          ))));
      await tester.pumpAndSettle();
    }

    testWidgets('a word with a recording has no 合成 mark on either accent',
        (tester) async {
      for (final (word, id) in [('eye', 7), ('owl', 8)]) {
        await pumpBack(tester, _word(word, lexemeId: id));
        // 問題回報 #1123: one recording for both accents, one button.
        expect(find.text('英式'), findsNothing, reason: word);
        expect(find.text('美式'), findsNothing, reason: word);
        expect(find.byIcon(Icons.volume_up_outlined), findsOneWidget);
        expect(find.text('合成'), findsNothing, reason: word);
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets('a word with no recording marks both accents 合成',
        (tester) async {
      await pumpBack(tester, _word('zebu', lexemeId: 9));
      expect(find.byKey(const ValueKey('accent-tts-en-GB')), findsOneWidget);
      expect(find.byKey(const ValueKey('accent-tts-en-US')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the 英式 button plays the real recording, the flip plays it once',
        (tester) async {
      final speaker = _SlowSpeaker();
      await pumpApp(tester, initialTab: AppTab.settings, speaker: speaker);
      final context = tester.element(find.byType(Scaffold).first);
      for (final (word, id) in [('eye', 7), ('owl', 8)]) {
        speaker.said.clear();
        final run = playBothAccents(context, _word(word, lexemeId: id));
        await tester.pump();
        speaker.finishAll();
        await run;
        expect(speaker.said, hasLength(1), reason: word);
        expect(cardAccentAudioUrl(_word(word, lexemeId: id), 'en-GB'),
            endsWith('$word.mp3'));
      }
    });
  });

  test('the predicted next card and photo are the ones that come up (#726)',
      () {
    final repo = testRepository();
    final s = FlashcardSession(repo, continuous: true, random: Random(3));
    var checked = 0;
    for (var i = 0; i < 8 && !s.finished; i++) {
      final next = s.upcomingCards(cards: 1).firstOrNull;
      final photo =
          next == null ? null : s.plannedPhotos(next.wordEntryId).firstOrNull;
      // The flattened list keeps its old meaning.
      expect(s.upcomingPhotos(cards: 2, perCard: 1), [
        for (final c in s.upcomingCards(cards: 2))
          ...s.plannedPhotos(c.wordEntryId).take(1),
      ]);
      s.showAnswer();
      s.rate(Rating.good);
      if (next == null || s.finished) continue;
      expect(s.card?.id, next.id);
      if (photo != null) {
        expect(s.photo?.id, photo.id);
        checked++;
      }
    }
    expect(checked, greaterThan(0));
    s.dispose();
  });
}
