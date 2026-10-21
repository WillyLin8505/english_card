import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart' show AppTab;
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;

/// 卡 #226 第 112 輪: the photo-recall front showed 「空白鍵」 next to 顯示答案
/// on phones, which have no space key. The hint is for desktop only
/// (_hasKeyboard in flashcard_session_views.dart).
void main() {
  tearDown(() => LexiconPack.instance.clear());

  Future<void> openPhotoRecall(WidgetTester tester) async {
    final lexicon = pack([image(1)]);
    // The screen finds the photo through the loaded pack.
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        }
      ],
      'catalog_images': [image(1)]
    });
    final repo = repository(lexicon);
    await pumpApp(tester, initialTab: AppTab.review, repository: repo);
    await tester.tap(find.text('綜合'));
    await tester.pump();
    expect(find.text('顯示答案'), findsOneWidget);
  }

  testWidgets('phone: no space-key hint on 顯示答案', (tester) async {
    await openPhotoRecall(tester);
    expect(find.text('需要提示'), findsOneWidget, reason: '母語說明＋照片題');
    expect(find.text('空白鍵'), findsNothing);
  });

  testWidgets('desktop: the space-key hint stays', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    try {
      await openPhotoRecall(tester);
      expect(find.text('需要提示'), findsOneWidget);
      expect(find.text('空白鍵'), findsOneWidget);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });
}
