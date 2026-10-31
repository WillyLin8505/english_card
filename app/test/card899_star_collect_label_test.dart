import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'helpers.dart';

// 卡 #899: ☆ on a photo word collects it (單字收集區 → 單字庫 on 儲存); the
// accessibility text must not say 鎖定 any more.
void main() {
  const oldLock = '鎖定（調整難度時保留）';
  const oldUnlock = '取消鎖定';
  const collect = '收集單字（按儲存後加入單字庫）';
  const uncollect = '取消收集單字';
  final cjk = RegExp(r'[一-鿿]');

  testWidgets('photo word ☆ says collect, then remove from collection',
      (tester) async {
    final app = await pumpApp(tester, size: const Size(360, 740));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    final row = find.byKey(const ValueKey('word:apple'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();

    expect(find.bySemanticsLabel(oldLock), findsNothing);
    final star = find.descendant(
        of: row, matching: find.bySemanticsLabel(collect));
    expect(star, findsOneWidget);

    await tester.tap(star);
    await tester.pumpAndSettle();
    expect(find.descendant(of: row, matching: find.bySemanticsLabel(uncollect)),
        findsOneWidget);
    expect(find.descendant(of: row, matching: find.bySemanticsLabel(oldUnlock)),
        findsNothing);
    expect(tester.takeException(), isNull);
  });

  test('collect labels exist in zh-TW, English and French', () {
    expect(uiCatalog.containsKey(oldLock), isFalse);
    expect(uiCatalog.containsKey(oldUnlock), isFalse);
    expect(translateUi(collect, 'zh-TW'), collect);
    expect(translateUi(uncollect, 'zh-TW'), uncollect);
    for (final language in const ['en', 'fr']) {
      for (final source in [collect, uncollect]) {
        final out = translateUi(source, language);
        expect(cjk.hasMatch(out), isFalse, reason: '$language: $source → $out');
        expect(out, isNot(contains('lock')), reason: '$language: $out');
      }
    }
  });
}
