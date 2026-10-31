import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/card_report.dart';

import 'helpers.dart';

void main() {
  testWidgets('設定 目錄 jumps to a section; 關於 shows version', (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 800));
    final scrollable = find.byType(Scrollable).first;
    final top = tester.state<ScrollableState>(scrollable).position.pixels;

    await tester.tap(find.byKey(const ValueKey('settings-toc-關於')));
    await tester.pumpAndSettle();
    expect(tester.state<ScrollableState>(scrollable).position.pixels,
        greaterThan(top));
    expect(find.byKey(const ValueKey('about-version')), findsOneWidget);
    expect(find.textContaining(CardReport.appVersion.split('+').first),
        findsWidgets);
  });

  test('appVersion default matches pubspec', () {
    final line = File('pubspec.yaml')
        .readAsLinesSync()
        .firstWhere((l) => l.startsWith('version:'));
    expect(line.split(':').last.trim(), CardReport.appVersion);
  });
}
