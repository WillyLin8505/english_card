// 問題回報 #956 / 卡 #839: iPad 點「複習」分頁整個卡死（單字本 65 字、17 張照片、
// 9 筆複習紀錄，大部分字沒有到期卡）。This builds that shape and opens the tab.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordDatabaseRepository _sixtyFive() {
  final repo = WordDatabaseRepository(clock: () => testNow);
  final words = [
    for (var i = 0; i < 65; i++)
      repo.addWord(word: 'word$i', pos: 'noun', meaning: '字$i', level: 'A1'),
  ];
  for (var i = 0; i < 17; i++) {
    repo.addPhoto(Photo(
        id: 'p$i',
        title: '',
        takenAt: testNow,
        createdAt: testNow,
        placeholderColors: const [0xFFB8C4D6, 0xFFDDE4EE]));
  }
  // Grade 9 cards so FSRS pushes them into the future.
  for (var i = 0; i < 9; i++) {
    final s = FlashcardSession(repo, focus: [repo.cardOf(words[i].id)!.id]);
    s.showAnswer();
    s.rate(Rating.good);
    s.dispose();
  }
  return repo;
}

void main() {
  test('session over 65 words finishes picking and upcoming', () {
    final repo = _sixtyFive();
    final s = FlashcardSession(repo, continuous: true);
    for (var i = 0; i < 300 && !s.finished; i++) {
      s.upcomingCards(cards: 5);
      s.upcomingPhotos();
      s.showAnswer();
      s.rate(Rating.good);
    }
    s.dispose();
  }, timeout: const Timeout(Duration(seconds: 30)));

  testWidgets('opening the 複習 tab returns', (tester) async {
    await pumpApp(tester, initialTab: AppTab.review, repository: _sixtyFive());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('綜合'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }, timeout: const Timeout(Duration(seconds: 60)));
}
