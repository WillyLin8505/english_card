import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:photo_english_app/theme/card_style.dart';
import 'package:photo_english_app/widgets/card_style_picker.dart';

void main() {
  testWidgets('每個樣式都有預覽，點選會回報', (tester) async {
    CardStyle? picked;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: CardStylePicker(
              selected: CardStyle.classic, onChanged: (s) => picked = s),
        ),
      ),
    ));
    expect(find.text('apple'), findsNWidgets(CardStyle.values.length));
    expect(find.text('經典'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('cardStyle-playful')));
    expect(picked, CardStyle.playful);
  });
}
