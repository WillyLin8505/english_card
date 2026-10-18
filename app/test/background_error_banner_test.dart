import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/background_errors.dart';
import 'package:photo_english_app/widgets/background_error_banner.dart';

void main() {
  tearDown(() => BackgroundErrors.instance.dismiss());

  testWidgets(
      '問題回報 #175: a reported background failure shows above the screen, '
      'with a working 重試 and 關閉', (tester) async {
    final errors = BackgroundErrors();
    var retried = false;
    await tester.pumpWidget(MaterialApp(
        builder: (context, child) =>
            BackgroundErrorBanner(errors: errors, child: child!),
        home: const Scaffold(body: Text('photos'))));
    expect(find.text('詞庫同步失敗'), findsNothing);

    errors.report('sync', '詞庫同步失敗',
        retry: () async {
          retried = true;
        });
    await tester.pump();
    expect(find.text('詞庫同步失敗'), findsOneWidget);
    expect(find.text('photos'), findsOneWidget);

    await tester.tap(find.text('重試'));
    await tester.pump();
    expect(retried, isTrue);
    expect(find.text('詞庫同步失敗'), findsNothing);
  });

  testWidgets('關閉 dismisses without calling retry', (tester) async {
    final errors = BackgroundErrors();
    var retried = false;
    await tester.pumpWidget(MaterialApp(
        builder: (context, child) =>
            BackgroundErrorBanner(errors: errors, child: child!),
        home: const Scaffold(body: Text('photos'))));
    errors.report('sync', '詞庫同步失敗', retry: () async => retried = true);
    await tester.pump();
    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();
    expect(find.text('詞庫同步失敗'), findsNothing);
    expect(retried, isFalse);
  });

  testWidgets('a second source cannot clear the first source\'s message',
      (tester) async {
    final errors = BackgroundErrors();
    await tester.pumpWidget(MaterialApp(
        builder: (context, child) =>
            BackgroundErrorBanner(errors: errors, child: child!),
        home: const Scaffold(body: Text('photos'))));
    errors.report('a', '來源 A 失敗');
    await tester.pump();
    errors.clear('b');
    await tester.pump();
    expect(find.text('來源 A 失敗'), findsOneWidget);
    errors.clear('a');
    await tester.pump();
    expect(find.text('來源 A 失敗'), findsNothing);
  });
}
