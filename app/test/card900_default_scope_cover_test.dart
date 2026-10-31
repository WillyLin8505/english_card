import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';

void main() {
  for (final scope in ['all', 'new', 'weak']) {
    testWidgets('default cover for $scope is designed, not a plain block',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
          home: SizedBox(width: 120, height: 120, child: DefaultScopeCover(scope))));
      expect(find.byKey(const ValueKey('default-scope-cover')), findsOneWidget);
      expect(find.byType(Icon), findsOneWidget);
    });
  }
}
