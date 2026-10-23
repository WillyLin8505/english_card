// 問題回報 #648: a downloaded 單字集 adds words but no 相片冊, so 複習 had no
// tile for it. It now has one, and it reviews only that deck's words.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/widgets/mobile/photo_cache.dart';

import 'helpers.dart';

void main() {
  late DeckLibrary previous;
  setUp(() => previous = DeckLibrary.instance);
  tearDown(() => DeckLibrary.instance = previous);

  testWidgets('a word deck is a 複習 tile that reviews its own words',
      (tester) async {
    final lib = DeckLibrary(remote: false, persist: false);
    DeckLibrary.instance = lib;
    final app = await pumpApp(tester,
        initialTab: AppTab.words, size: const Size(402, 1600));
    final repo = app.repository;
    final created = await lib.install(
        const DeckContent(
            DeckInfo(
                slug: 'ngsl',
                kind: 'words',
                title: '基礎 3000 字',
                count: 2,
                coverAssetId: 5),
            words: [
              (word: 'zebra', pos: 'noun', level: 'A2'),
              (word: 'kite', pos: 'noun', level: 'A2'),
            ]),
        repository: repo,
        intake:
            AppScope.of(tester.element(find.byType(Scaffold).first)).intake);
    expect(created, hasLength(2));
    for (final e in created) {
      repo.applyWordData(e.id,
          meaning: e.word == 'zebra' ? '斑馬' : '風箏',
          status: WordDataStatus.complete);
    }

    app.navigator.selectTab(AppTab.review);
    await tester.pumpAndSettle();
    expect(find.text('想複習哪一本？'), findsOneWidget);
    expect(find.text('基礎 3000 字'), findsOneWidget);
    expect(find.text('今天 2 張'), findsWidgets);
    // The deck's cover picture is the tile's picture.
    expect(
        find.byWidgetPredicate((w) =>
            w is Image &&
            w.image is CachedNetworkPhoto &&
            (w.image as CachedNetworkPhoto).url.contains('id=5')),
        findsOneWidget);

    await tester.tap(find.text('基礎 3000 字'));
    await tester.pumpAndSettle();
    expect(app.settings.reviewScope, 'deck:ngsl');
    final words = <String>{};
    for (var i = 0; i < 2; i++) {
      final front = find.byType(FlashcardFront);
      if (front.evaluate().isEmpty) break;
      final w = tester.widget<FlashcardFront>(front);
      words.add(w.entry.word);
      final s = w.session;
      if (s != null && !s.canAnswer) s.reportPhotoState(s.photoAttempt, true);
      s?.showAnswer();
      await tester.pumpAndSettle();
      await tester.tap(find.text('記得'));
      await tester.pumpAndSettle();
    }
    expect(words, {'zebra', 'kite'});
  });
}
