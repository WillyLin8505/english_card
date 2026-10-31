// Owner 2026-10-23: the first pronunciation after a flip was a robotic TTS
// voice — British is played first but most words only have an American
// recording. A flip now plays only recorded accents, and TTS picks the
// best installed voice.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';

import 'helpers.dart';

class _RecordingSpeaker extends SilentSpeaker {
  final calls = <(String, String?)>[];
  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    calls.add((accent, audioUrl));
    return super
        .say(text, language: language, audioUrl: audioUrl, accent: accent);
  }
}

Map<String, dynamic> _lexeme(int id, String lemma, List<String> accents) => {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': 'noun',
      'pronunciations': [
        for (final (i, a) in accents.indexed)
          {
            'kind': 'audio',
            'accent': a,
            if (i == 0) 'default': true,
            'audio': 'audio/en/$lemma-$a.mp3',
          },
      ],
    };

WordEntry _word(String word) => WordEntry(
    id: 'w-$word',
    word: word,
    pos: 'noun',
    meaning: '',
    createdAt: testNow,
    updatedAt: testNow);

void main() {
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('a flip plays recorded accents first, then the other in TTS',
      (tester) async {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lexeme(1, 'water', ['UK', 'US']),
        _lexeme(2, 'yak', ['US']),
        _lexeme(3, 'zebu', []),
      ],
    });
    final speaker = _RecordingSpeaker();
    await pumpApp(tester, initialTab: AppTab.settings, speaker: speaker);
    final context = tester.element(find.byType(Scaffold).first);

    await playBothAccents(context, _word('water'));
    expect(speaker.calls.map((c) => c.$1), ['en-GB', 'en-US']);
    expect(speaker.calls.every((c) => c.$2 != null), isTrue);

    // Only an American recording: it stands for both accents and is heard
    // twice, no robotic TTS after it (問題回報 #724, #1122).
    speaker.calls.clear();
    await playBothAccents(context, _word('yak'));
    expect(speaker.calls.map((c) => c.$1), ['en-US', 'en-GB']);
    expect(speaker.calls.every((c) => c.$2!.endsWith('yak-US.mp3')), isTrue);

    // No recording at all: both accents in TTS.
    speaker.calls.clear();
    await playBothAccents(context, _word('zebu'));
    expect(speaker.calls, [('en-GB', null), ('en-US', null)]);
  });

  test('bestTtsVoice prefers premium, then enhanced, never novelty voices', () {
    final voices = [
      {
        'name': 'Daniel',
        'locale': 'en-GB',
        'quality': 'default',
        'identifier': 'com.apple.voice.compact.en-GB.Daniel'
      },
      {
        'name': 'Bubbles',
        'locale': 'en-US',
        'quality': 'premium',
        'identifier': 'com.apple.speech.synthesis.voice.Bubbles'
      },
      {
        'name': 'Eddy',
        'locale': 'en-US',
        'quality': 'enhanced',
        'identifier': 'com.apple.eloquence.en-US.Eddy'
      },
      {
        'name': 'Samantha',
        'locale': 'en-US',
        'quality': 'enhanced',
        'identifier': 'com.apple.voice.enhanced.en-US.Samantha'
      },
      {
        'name': 'Ava',
        'locale': 'en-US',
        'quality': 'premium',
        'identifier': 'com.apple.voice.premium.en-US.Ava'
      },
      {
        'name': 'Serena',
        'locale': 'en_GB',
        'quality': 'enhanced',
        'identifier': 'com.apple.voice.enhanced.en-GB.Serena'
      },
    ];
    expect(bestTtsVoice(voices, 'en-US')?['name'], 'Ava');
    expect(bestTtsVoice(voices, 'en-GB')?['name'], 'Serena');
    // Only default-quality voices: keep the platform's default.
    expect(bestTtsVoice(voices.take(1).toList(), 'en-GB'), isNull);
    expect(bestTtsVoice(voices, 'fr-FR'), isNull);
    expect(
        bestTtsVoice([
          null,
          'x',
          {'locale': 'en-US'}
        ], 'en-US'),
        isNull);
  });
}
