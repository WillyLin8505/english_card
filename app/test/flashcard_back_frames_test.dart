import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

// 問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）: the frame
// that turns the card has the word and its meaning; the sound buttons come
// the next frame, then the photo, then the sections under it one per frame.
void main() {
  testWidgets('翻卡：發音按鈕、照片依序晚一個畫面出現，下方區塊一個畫面一個', (tester) async {
    final entry = WordEntry(
      id: 'w-sunlight',
      word: 'sunlight',
      pos: 'noun',
      meaning: '陽光',
      level: 'A2',
      forms: const [WordForm('sunlights', 'plural')],
      root: 'sun',
      affixes: const ['light'],
      examples: const [
        WordExample(
            text: 'The sunlight warms the sea.', translation: '陽光曬暖了海。'),
      ],
      createdAt: testNow,
      updatedAt: testNow,
    );
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [entry]);
    final photo = Photo(
      id: 'p1',
      title: '',
      takenAt: testNow,
      createdAt: testNow,
      placeholderColors: const [0xFFB8C4D6, 0xFFDDE4EE],
    );
    final turned = ValueNotifier(false);
    await pumpApp(tester,
        repository: repo,
        size: const Size(402, 2000),
        home: Scaffold(
            body: SingleChildScrollView(
                child: ValueListenableBuilder(
          valueListenable: turned,
          builder: (context, back, _) => !back
              ? const SizedBox.shrink()
              : FlashcardBack(
                  entry: entry,
                  card: const LearningCard(
                      id: 'card', wordEntryId: 'w-sunlight', templateId: 't'),
                  photo: photo,
                  anchor: const LabelPoint(0.3, 0.4),
                  photos: [(photo, const LabelPoint(0.3, 0.4), null)],
                  template: repo.template,
                  learnerLevel: 'A2',
                  onPlay: () {},
                  onOpen: () {},
                ),
        ))));
    turned.value = true;
    await tester.pump();

    // The turning frame: the word and its meaning; the photo's place is
    // held at its full height.
    expect(find.text(displayWord('sunlight')), findsOneWidget);
    expect(find.text('陽光'), findsOneWidget);
    expect(find.byType(PinnedPhoto), findsNothing);
    expect(find.text('例句與翻譯'), findsNothing);

    expect(find.byTooltip('播放英式發音'), findsNothing);

    // Next frame: the sound buttons; then the photo.
    await tester.pump();
    expect(find.byTooltip('播放英式發音'), findsOneWidget);
    expect(find.byTooltip('播放美式發音'), findsOneWidget);
    expect(find.byType(PinnedPhoto), findsNothing);
    await tester.pump();
    expect(find.byType(PinnedPhoto), findsOneWidget);
    expect(find.text('例句與翻譯'), findsNothing);

    // Then one section per frame, in order.
    await tester.pump();
    expect(find.text('例句與翻譯'), findsOneWidget);
    expect(find.text('詞形變化'), findsNothing);
    await tester.pump();
    expect(find.text('詞形變化'), findsOneWidget);
    expect(find.text('構詞拆解'), findsNothing);
    await tester.pump();
    expect(find.text('構詞拆解'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.byType(PinnedPhoto), findsOneWidget);
    expect(find.text('構詞拆解'), findsOneWidget);
  });
}
