import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 問題回報 #404: the app shows only what the learner owns; album groups are
// worked out from the albums, not a fixed list.
void main() {
  testWidgets('tabs show one 單字本 and one 相片冊, no 資料庫 switch',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words);
    expect(find.text('資料庫'), findsNothing);
    expect(find.text('我的單字本'), findsWidgets);
    await pumpApp(tester, initialTab: AppTab.album);
    expect(find.text('資料庫'), findsNothing);
    expect(find.text('資料庫相片冊'), findsNothing);
  });

  testWidgets('no fixed category pills: only groups that exist',
      (tester) async {
    // A learner with no albums yet (the sample data owns a 客廳 album).
    await pumpApp(tester,
        initialTab: AppTab.album,
        repository: WordDatabaseRepository(clock: () => testNow));
    for (final c in ['廚房', '客廳', '戶外', '食物', '動物']) {
      expect(find.text(c), findsNothing, reason: '$c is not a pre-made pill');
    }
    expect(find.text('全部'), findsOneWidget);
    expect(find.text('還沒有相片：去拍照，或到卡片集下載圖片集'), findsOneWidget);
  });

  test('albums are grouped by content, deck, or month; rename keeps data', () {
    final repo = testRepository();
    final deck = repo.addAlbum(name: '別人的圖片集', deckSlug: 'x', author: 'a');
    final plain = repo.addAlbum(name: '週末');
    expect(repo.albumGroup(deck), deckAlbumGroup);
    expect(repo.albumGroup(plain), '${testNow.year} 年 ${testNow.month} 月');
    expect(repo.albumGroups(), containsAll([deckAlbumGroup]));
    repo.renameAlbum(plain.id, '  海邊  ');
    expect(repo.album(plain.id)!.name, '海邊');
    expect(repo.album(plain.id)!.createdAt, plain.createdAt);
  });

  test('old saved albums (category, no deck fields) load and keep their group',
      () {
    final old = Album.fromJson({
      'id': 'a1',
      'name': '早餐',
      'category': '食物',
      'coverAsset': null,
      'createdAt': '2026-01-02T03:04:05.000',
    });
    expect(old.deckSlug, isNull);
    expect(Album.fromJson(old.toJson()).category, '食物');
    final repo = testRepository();
    expect(repo.albumGroup(old), '食物');
  });
}
