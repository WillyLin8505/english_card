// Windows 卡 #584/#695/#759 (owner 「用 Azure 抓語音」): Azure neural-voice
// files come into the pack as pronunciations marked synthetic. An accent
// plays 1) a real recording in that accent, 2) a real recording in another
// accent, 3) an Azure file (same accent first, else any), 4) the phone's
// TTS; 「合成」 is shown for 3 and 4, and an Azure file is credited as
// 「Azure 神經語音（合成）」 rather than a speaker and license.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/accent_audio.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/widgets/recording_credit.dart';

import 'helpers.dart';

class _RecordingSpeaker implements Speaker {
  final said = <(String accent, String? url)>[];

  @override
  Future<bool> say(String text,
      {required String language, String? audioUrl, String accent = 'en-GB'}) {
    said.add((accent, audioUrl));
    return Future.value(true);
  }

  @override
  Future<void> stop() async {}
}

Map<String, dynamic> _audio(String lemma, String? accent,
        {Map<String, dynamic> flag = const {}, bool isDefault = false}) =>
    {
      'kind': 'audio',
      'accent': accent,
      'default': isDefault,
      'audio':
          'audio/en/$lemma-${accent ?? 'x'}${flag.isEmpty ? '' : '-tts'}.mp3',
      'speaker': 'Jane Doe',
      'license': 'CC BY-SA 4.0',
      ...flag,
    };

Map<String, dynamic> _pack() => {
      'schema_version': 5,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': 'v1',
      'lexemes': [
        // 1: real in both accents, plus an Azure US file.
        {
          'id': 1,
          'lemma': 'cat',
          'normalized': 'cat',
          'pos': 'noun',
          'status': 'full',
          'pronunciations': [
            _audio('cat', 'US', flag: {'source': 'tts'}, isDefault: true),
            _audio('cat', 'UK'),
            _audio('cat', 'US'),
          ],
        },
        // 2: a real US recording, an Azure UK file.
        {
          'id': 2,
          'lemma': 'dog',
          'normalized': 'dog',
          'pos': 'noun',
          'status': 'full',
          'pronunciations': [
            _audio('dog', 'UK', flag: {'source': 'Azure'}, isDefault: true),
            _audio('dog', 'US'),
          ],
        },
        // 3: only Azure files, one per accent.
        {
          'id': 3,
          'lemma': 'yak',
          'normalized': 'yak',
          'pos': 'noun',
          'status': 'full',
          'pronunciations': [
            _audio('yak', 'UK', flag: {'synthetic': true}),
            _audio('yak', 'US', flag: {'kind': 'tts_audio'}),
          ],
        },
        // 3 (any accent): one Azure US file.
        {
          'id': 4,
          'lemma': 'gnu',
          'normalized': 'gnu',
          'pos': 'noun',
          'status': 'full',
          'pronunciations': [
            _audio('gnu', 'US', flag: {'source': 'tts'}),
          ],
        },
        // 4: no file at all.
        {
          'id': 5,
          'lemma': 'zebu',
          'normalized': 'zebu',
          'pos': 'noun',
          'status': 'full',
        },
      ],
    };

WordEntry _word(String word, int id) => WordEntry(
    id: 'w-$word',
    word: word,
    pos: 'noun',
    meaning: '',
    lexemeId: id,
    createdAt: testNow,
    updatedAt: testNow);

void main() {
  tearDown(() => LexiconPack.instance.clear());

  group('parsing the synthetic flag', () {
    test('each accepted field marks a clip synthetic; none means real', () {
      for (final (flag, synthetic) in [
        (<String, dynamic>{}, false),
        ({'source': 'wikimedia'}, false),
        ({'source': 'tts'}, true),
        ({'source': 'TTS'}, true),
        ({'source': 'azure'}, true),
        ({'source': 'azure_tts'}, true),
        ({'synthetic': true}, true),
        ({'synthetic': false}, false),
        ({'kind': 'tts_audio'}, true),
      ]) {
        final d = LexDetail.fromJson({
          'pronunciations': [_audio('cat', 'US', flag: flag)],
        });
        expect(d.recordings.single.synthetic, synthetic, reason: '$flag');
        expect(d.recordingCredits.values.single.isSynthetic, synthetic,
            reason: '$flag');
      }
    });

    test('real recordings sort before synthetic ones, default first', () {
      final d = LexDetail.fromJson({
        'pronunciations': [
          _audio('cat', 'US', flag: {'source': 'tts'}, isDefault: true),
          _audio('cat', 'UK'),
          _audio('cat', 'US', isDefault: true),
        ],
      });
      expect([for (final r in d.recordings) r.synthetic], [false, false, true]);
      expect(d.audio, 'audio/en/cat-US.mp3');
      expect(d.audioCredit, 'CC BY-SA 4.0');
      final azureOnly = LexDetail.fromJson({
        'pronunciations': [
          _audio('gnu', 'US', flag: {'source': 'tts'})
        ],
      });
      expect(azureOnly.audioCredit, 'Azure 神經語音（合成）');
    });

    test('a JSON pack and the SQLite pack built from it agree', () {
      final dir = Directory.systemTemp.createTempSync('azure_tts_');
      addTearDown(() {
        try {
          dir.deleteSync(recursive: true);
        } on FileSystemException {
          // Windows keeps a handle for a moment.
        }
      });
      final path = '${dir.path}/pack.sqlite';
      LexiconSqlite.build(_pack(), path);
      final fromJson = LexiconPack()..loadJson(_pack());
      final fromDb = LexiconPack()..loadSqlite(path);
      expect(fromDb.fromSqlite, isTrue);
      for (final p in [fromJson, fromDb]) {
        List<(String?, bool)> recs(int id) =>
            [for (final r in p.byId(id)!.recordings) (r.accent, r.synthetic)];
        expect(recs(1), [('UK', false), ('US', false), ('US', true)]);
        expect(recs(2), [('US', false), ('UK', true)]);
        expect(recs(3), [('UK', true), ('US', true)]);
        expect(recs(4), [('US', true)]);
        expect(recs(5), isEmpty);
      }
      fromDb.clear();
    });
  });

  group('playback order', () {
    setUp(() => LexiconPack.instance.loadJson(_pack()));

    String? url(String word, int id, String accent) =>
        cardAccentAudioUrl(_word(word, id), accent);

    test('1) a real recording in the accent', () {
      expect(url('cat', 1, 'en-GB'), endsWith('cat-UK.mp3'));
      expect(url('cat', 1, 'en-US'), endsWith('cat-US.mp3'));
      expect(accentAudioRank(_word('cat', 1), 'en-US'), 0);
    });

    test('2) a real recording in another accent beats an Azure file', () {
      expect(url('dog', 2, 'en-GB'), endsWith('dog-US.mp3'));
      expect(accentAudioRank(_word('dog', 2), 'en-GB'), 1);
      // Without orDefault, the accent's own Azure file stands for it.
      expect(
          accentAudioUrl(_word('dog', 2), 'en-GB'), endsWith('dog-UK-tts.mp3'));
    });

    test('3) an Azure file, the same accent first, else any', () {
      expect(url('yak', 3, 'en-GB'), endsWith('yak-UK-tts.mp3'));
      expect(url('yak', 3, 'en-US'), endsWith('yak-US-tts.mp3'));
      expect(url('gnu', 4, 'en-GB'), endsWith('gnu-US-tts.mp3'));
      expect(accentAudioRank(_word('gnu', 4), 'en-GB'), 2);
    });

    test('4) the phone TTS when there is no file', () {
      expect(url('zebu', 5, 'en-GB'), isNull);
      expect(accentAudioRank(_word('zebu', 5), 'en-GB'), 3);
    });

    test('合成 is meant for 3 and 4 only', () {
      for (final accent in const ['en-GB', 'en-US']) {
        expect(accentAudioIsSynthetic(_word('cat', 1), accent), isFalse);
        expect(accentAudioIsSynthetic(_word('dog', 2), accent), isFalse);
        expect(accentAudioIsSynthetic(_word('yak', 3), accent), isTrue);
        expect(accentAudioIsSynthetic(_word('gnu', 4), accent), isTrue);
        expect(accentAudioIsSynthetic(_word('zebu', 5), accent), isTrue);
      }
    });

    test('an Azure file is credited as a synthetic voice', () {
      final cat = LexiconPack.instance.byId(1)!;
      expect(
          packAccentAudioCredit(cat, 'en-US')!.text, 'Jane Doe · CC BY-SA 4.0');
      final credit = accentAudioCredit(_word('yak', 3), 'en-GB')!;
      expect(credit.isSynthetic, isTrue);
      expect(RecordingCreditLine.label(credit), 'Azure 神經語音（合成）');
      expect(uiCatalog['Azure 神經語音（合成）'], (
        'Azure neural voice (synthetic)',
        'Voix neuronale Azure (synthèse)'
      ));
      // Step 2 plays a person, so the person is credited.
      expect(accentAudioCredit(_word('dog', 2), 'en-GB')!.isSynthetic, isFalse);
      expect(accentAudioCredit(_word('zebu', 5), 'en-GB'), isNull);
    });

    testWidgets('a flip plays real voices first and no file twice',
        (tester) async {
      final speaker = _RecordingSpeaker();
      await pumpApp(tester, initialTab: AppTab.settings, speaker: speaker);
      final context = tester.element(find.byType(Scaffold).first);
      Future<List<(String, String?)>> flip(String word, int id) async {
        speaker.said.clear();
        await playBothAccents(context, _word(word, id));
        return [...speaker.said];
      }

      var said = await flip('cat', 1);
      expect([for (final s in said) s.$1], ['en-GB', 'en-US']);
      expect(said.every((s) => !s.$2!.contains('-tts')), isTrue);
      // The real US clip stands for both accents: heard once, no Azure.
      said = await flip('dog', 2);
      expect(said, hasLength(1));
      expect(said.single.$2, endsWith('dog-US.mp3'));
      said = await flip('yak', 3);
      expect([for (final s in said) s.$2!.split('/').last],
          ['yak-UK-tts.mp3', 'yak-US-tts.mp3']);
      said = await flip('gnu', 4);
      expect(said, hasLength(1));
      said = await flip('zebu', 5);
      expect([for (final s in said) s.$2], [null, null]);
    });

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

    testWidgets('the card back marks 合成 on Azure and TTS accents only',
        (tester) async {
      for (final (word, id, marked) in [
        ('cat', 1, false),
        ('dog', 2, false),
        ('yak', 3, true),
        ('gnu', 4, true),
        ('zebu', 5, true),
      ]) {
        await pumpBack(tester, _word(word, id));
        for (final accent in const ['en-GB', 'en-US']) {
          // 問題回報 #1123: gnu's one file stands for both accents, so it
          // has a single (英式) button.
          final shown = !(word == 'gnu' && accent == 'en-US');
          expect(find.byKey(ValueKey('accent-tts-$accent')),
              marked && shown ? findsOneWidget : findsNothing,
              reason: '$word $accent');
        }
      }
      expect(tester.takeException(), isNull);
    });
  });
}
