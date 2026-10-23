// 問題回報 #657 (M138): a CC BY-SA recording credits its speaker and license
// where the word is shown.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/recording_credit.dart';

import 'helpers.dart';

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('the credit names the speaker (or attribution) and the license', () {
    expect(
        RecordingCredit.fromJson({
          'speaker': 'Jane Doe',
          'license': 'CC BY-SA 4.0',
          'source_page':
              'https://commons.wikimedia.org/wiki/File:En-us-apple.ogg'
        })!
            .text,
        'Jane Doe · CC BY-SA 4.0');
    // "Own work" says nothing about who: only the license.
    expect(
        RecordingCredit.fromJson(
                {'attribution': 'Own work', 'license': 'CC BY-SA 4.0'})!
            .text,
        'CC BY-SA 4.0');
    expect(RecordingCredit.fromJson({}), isNull);
    // M139: Wikimedia's multi-line speaker text becomes one name.
    expect(RecordingCredit.cleanSpeaker('Speaker: Jane Doe\nRecorder: John'),
        'Jane Doe');
    expect(
        RecordingCredit.cleanSpeaker('Recorder: John\nSpeaker: Jane'), 'Jane');
    expect(RecordingCredit.cleanSpeaker('Recorder: John'), 'John');
    expect(RecordingCredit.cleanSpeaker('Jane Doe'), 'Jane Doe');
    expect(
        RecordingCredit.cleanSpeaker('No machine-readable author provided. '
            'Chris Melville assumed (based on copyright claims).'),
        'Chris Melville');
    expect(RecordingCredit.cleanSpeaker('  \n '), isNull);
    expect(
        RecordingCredit.fromJson({
          'speaker': 'Speaker: Jane Doe\nRecorder: John',
          'license': 'CC BY-SA 4.0'
        })!
            .text,
        'Jane Doe · CC BY-SA 4.0');
    expect(
        RecordingCreditLine.label(const RecordingCredit('Jane · CC BY-SA 4.0',
            sourcePage: 'https://commons.wikimedia.org/wiki/File:x.ogg')),
        '發音錄音：Jane · CC BY-SA 4.0（commons.wikimedia.org）');
  });

  testWidgets('單字詳情 shows the recording credit', (tester) async {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'pronunciations': [
            {
              'kind': 'audio',
              'accent': 'UK',
              'default': true,
              'audio': 'audio/en/apple-uk.mp3',
              'speaker': 'Jane Doe',
              'license': 'CC BY-SA 4.0',
            }
          ],
        },
      ],
    });
    final app = await pumpApp(tester,
        initialTab: AppTab.words, size: const Size(402, 1400));
    app.navigator.openWord(app.repository.entryByWord('apple')!.id);
    await tester.pumpAndSettle();
    expect(find.text('發音錄音：Jane Doe · CC BY-SA 4.0'), findsOneWidget);
  });
}
