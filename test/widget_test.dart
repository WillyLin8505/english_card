import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:english_card/main.dart';

void main() {
  testWidgets('App shows initial screen with photo picker options',
      (WidgetTester tester) async {
    await tester.pumpWidget(const EnglishCardApp());

    expect(find.text('拍照學英文'), findsOneWidget);
    expect(find.text('選擇一張喜歡的照片'), findsOneWidget);
    expect(find.text('相簿'), findsOneWidget);
    expect(find.text('拍照'), findsOneWidget);
    expect(find.byIcon(Icons.photo_library), findsWidgets);
    expect(find.byIcon(Icons.camera_alt), findsOneWidget);
  });

  testWidgets('Bottom bar shows mock mode indicator', (WidgetTester tester) async {
    await tester.pumpWidget(const EnglishCardApp());

    expect(find.text('Mock 模式'), findsOneWidget);
    expect(find.byIcon(Icons.science), findsOneWidget);
  });
}
