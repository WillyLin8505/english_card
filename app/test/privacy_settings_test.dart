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
    expect(sw, findsOneWidget);
    await tester.ensureVisible(sw);
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
}
