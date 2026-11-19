// 問題回報 #1676 (card #1228): every example sentence has a play button —
// the recording when there is one, else (or when it fails) the system voice.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/speaker.dart';

import 'helpers.dart';

/// Records each say() and answers [result] (false: nothing could be played).
class _RecordingSpeaker extends SilentSpeaker {
  _RecordingSpeaker({this.result = true});

  final bool result;
  final calls = <(String, String, String?)>[];

  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    calls.add((text, language, audioUrl));
    return result;
  }
}

Future<TestApp> _pumpExample(
        WidgetTester tester, Speaker speaker, WordExample example) =>
    pumpApp(
      tester,
      speaker: speaker,
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: ExampleText(example: example),
        ),
      ),
    );

void main() {
  const sentence = 'Il fait beau aujourd’hui.';

  testWidgets('a sentence with a recording plays that recording',
      (tester) async {
    final speaker = _RecordingSpeaker();
    final app = await _pumpExample(
        tester,
        speaker,
        const WordExample(
            text: sentence,
            translation: '今天天氣很好。',
            audioUrl: 'https://example.test/sentence.mp3'));

    await tester.tap(find.byIcon(Icons.volume_up_outlined));
    await tester.pumpAndSettle();

    expect(speaker.calls, [
      (sentence, app.repository.language, 'https://example.test/sentence.mp3'),
    ]);
  });

  testWidgets(
      'a sentence without a recording still has a play button that '
      'reads the sentence aloud', (tester) async {
    final speaker = _RecordingSpeaker();
    final app = await _pumpExample(tester, speaker,
        const WordExample(text: sentence, translation: '今天天氣很好。'));

    expect(find.byIcon(Icons.volume_up_outlined), findsOneWidget);
    await tester.tap(find.byIcon(Icons.volume_up_outlined));
    await tester.pumpAndSettle();

    // No URL: Speaker.say speaks the whole sentence with the system voice.
    expect(speaker.calls, [(sentence, app.repository.language, null)]);
  });

  testWidgets(
      'when neither the recording nor the voice can play, the learner '
      'is told', (tester) async {
    final speaker = _RecordingSpeaker(result: false);
    await _pumpExample(
        tester,
        speaker,
        const WordExample(
            text: sentence,
            translation: '今天天氣很好。',
            audioUrl: 'https://example.test/broken.mp3'));

    await tester.tap(find.byIcon(Icons.volume_up_outlined));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(speaker.calls.single.$3, 'https://example.test/broken.mp3');
    expect(find.text('播放發音失敗，請檢查音量或稍後再試'), findsOneWidget);
  });
}
