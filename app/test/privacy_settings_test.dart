import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/privacy_policy_screen.dart';
import 'package:photo_english_app/services/analytics.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

void main() {
  tearDown(() => Analytics.instance.sharing = false);

  testWidgets('usage stats stay off until the switch, and the policy opens',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 2200));
    expect(app.settings.shareUsageStats, isFalse);
    expect(Analytics.instance.sharing, isFalse);

    // The 隱私 card's switch (設定 also has the photo-label switch).
    final sw = find.byKey(const ValueKey('usage-stats-switch'));
    await tester.scrollUntilVisible(sw, 300,
        scrollable: find.byType(Scrollable).first);
    expect(sw, findsOneWidget);
    await tester.ensureVisible(sw);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -250));
    await tester.pumpAndSettle();
    expect(tester.widget<Switch>(sw).value, isFalse);

    await tester.tap(sw);
    await tester.pump();
    expect(app.settings.shareUsageStats, isTrue);
    expect(Analytics.instance.sharing, isTrue);

    await tester.tap(find.text('查看隱私權政策'));
    await tester.pumpAndSettle();
    expect(find.text('照片與辨識'), findsOneWidget);
    expect(
        find.text(PrivacyPolicyScreen.sections
            .firstWhere((s) => s.$1 == '照片與辨識')
            .$2),
        findsOneWidget);

    await tester.tap(find.descendant(
        of: find.byType(PrivacyPolicyScreen),
        matching: find.byType(BackNavButton)));
    await tester.pumpAndSettle();
    expect(find.text('分享使用統計'), findsOneWidget);
  });

  test('docs/privacy.html carries every in-app section verbatim (card #1010)',
      () {
    final html = File('../docs/privacy.html').readAsStringSync();
    String plain(String t) => t.replaceAll('&', '&amp;').replaceAll('<', '&lt;');
    for (final s in PrivacyPolicyScreen.sections.skip(1)) {
      expect(html, contains('<h2>${plain(s.$1)}</h2>'));
      expect(html, contains(plain(s.$2).replaceAll(
          'sssss971412@gmail.com',
          '<a href="mailto:sssss971412@gmail.com">sssss971412@gmail.com</a>')));
    }
    expect(html, contains(plain(PrivacyPolicyScreen.sections.first.$2)));
    // The five things 5.1.1(i) / 5.1.2(i) review asked for.
    for (final t in ['帳號資料', '雲端備份與同步', '意見回饋與卡片回報', '網路連線與第三方', '保存與刪除']) {
      expect(PrivacyPolicyScreen.sections.map((s) => s.$1), contains(t));
    }
  });
}
