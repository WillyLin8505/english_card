// 問題回報 #510 (card #502): 設定's 發音腔調 is heard where it applies, and
// choosing it plays a sample word.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/accent_audio.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';

import 'helpers.dart';

class _RecordingSpeaker extends SilentSpeaker {
  final calls = <(String, String, String?)>[];
  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    calls.add((text, accent, audioUrl));
    return super.say(text, language: language, audioUrl: audioUrl, accent: accent);
  }
}

Map<String, dynamic> _lexeme(int id, String lemma, List<String?> accents) => {
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
            'audio': 'audio/en/$lemma-${a ?? 'none'}.mp3',
          },
      ],
    };

void _loadPack() => LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lexeme(1, 'water', ['UK', 'US']),
        _lexeme(2, 'balcony', ['US', 'UK']),
        _lexeme(3, 'zebra', ['US', null]),
        _lexeme(4, 'yak', ['US']),
      ],
    });

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('a word plays the recording in the chosen accent, never the other one',
      () {
    _loadPack();
    String? url(String word, String accent) => accentAudioUrl(
        WordEntry(
            id: 'w',
            word: word,
            pos: 'noun',
            meaning: '',
            createdAt: DateTime(2026),
            updatedAt: DateTime(2026)), accent,
        allowUnlabelled: true);
    expect(url('balcony', 'en-GB'), endsWith('balcony-UK.mp3'));
    expect(url('balcony', 'en-US'), endsWith('balcony-US.mp3'));
    // No British recording: an unlabelled one, else TTS (null).
    expect(url('zebra', 'en-GB'), endsWith('zebra-none.mp3'));
    expect(url('yak', 'en-GB'), isNull);
    expect(url('yak', 'en-US'), endsWith('yak-US.mp3'));
  });

  testWidgets('choosing an accent in 設定 plays "water" in it, with a note',
      (tester) async {
    _loadPack();
    final speaker = _RecordingSpeaker();
    final app =
        await pumpApp(tester, initialTab: AppTab.settings, speaker: speaker);
    expect(find.textContaining('複習卡正面的發音都用這個腔調'), findsOneWidget);

    await tester.tap(find.text('美式（en-US）'));
    await tester.pump();
    expect(app.settings.englishAccent, 'en-US');
    expect(speaker.calls.last.$1, 'water');
    expect(speaker.calls.last.$2, 'en-US');
    expect(speaker.calls.last.$3, endsWith('water-US.mp3'));

    await tester.tap(find.text('英式（en-GB）'));
    await tester.pump();
    expect(speaker.calls.last.$3, endsWith('water-UK.mp3'));
  });

  testWidgets('the word page plays the 設定 accent, not the default recording',
      (tester) async {
    _loadPack();
    final speaker = _RecordingSpeaker();
    final app = await pumpApp(tester,
        speaker: speaker,
        settings: AppSettings.inMemory(englishAccent: 'en-GB'));
    app.navigator.openWord('w-balcony');
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('播放發音').first);
    await tester.pump();
    expect(speaker.calls.last.$2, 'en-GB');
    expect(speaker.calls.last.$3, endsWith('balcony-UK.mp3'));
  });
}
