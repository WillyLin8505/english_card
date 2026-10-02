import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/app/phone_frame.dart';
import 'package:photo_english_app/main.dart' as app;

import 'helpers.dart';

void main() {
  testWidgets('first web frame tolerates a temporarily null route child',
      (tester) async {
    tester.view.physicalSize = const Size(402, 874);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) => app.phoneFrameBuilder(context, null)),
    ));

    expect(find.byType(PhoneFrame), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the five tabs switch screens', (tester) async {
    await pumpApp(tester);
    expect(find.text('拍照學單字'), findsOneWidget);

    await tester.tap(find.text('相片冊'));
    await tester.pumpAndSettle();
    expect(find.text('我的相片冊'), findsOneWidget);

    await tester.tap(find.text('複習'));
    await tester.pumpAndSettle();
    expect(find.text('想複習的時候就開始吧'), findsOneWidget);

    await tester.tap(find.text('單字本'));
    await tester.pumpAndSettle();
    expect(find.text('我的單字本'), findsOneWidget);

    await tester.tap(find.text('設定'));
    await tester.pumpAndSettle();
    expect(find.text('目前程度 入門（A1）'), findsOneWidget);
  });

  testWidgets('a word\'s 出現這個單字的照片 opens its photo in the 相片冊 tab',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.words);
    app.navigator.openWord('w-balcony');
    await tester.pumpAndSettle();
    expect(find.text('出現這個單字的照片（6）'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel(RegExp('^開啟照片「晨光陽台」')));
    await tester.pumpAndSettle();
    expect(find.text('照片詳情'), findsOneWidget);
    expect(find.text('Balcony'), findsWidgets);
  });
}
