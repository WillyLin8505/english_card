import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/photo_picker_screen.dart';

import 'helpers.dart';

/// 問題回報 #1536 (審查 5.1.1(iii)): opening 選擇照片 must not ask for the
/// whole photo library. 最近照片 asks only after 顯示最近照片 is tapped, and
/// a denial is never asked again on its own.
void main() {
  const channel = MethodChannel('com.fluttercandies/photo_manager');

  // PermissionState indexes in photo_manager: notDetermined 0, restricted 1,
  // denied 2, authorized 3, limited 4.
  const notDetermined = 0;
  const denied = 2;
  const authorized = 3;

  late List<String> calls;
  late int currentState;
  late int requestResult;

  setUp(() {
    calls = [];
    currentState = notDetermined;
    requestResult = authorized;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      switch (call.method) {
        case 'getPermissionState':
          return currentState;
        case 'requestPermissionExtend':
          currentState = requestResult;
          return requestResult;
        case 'getAssetPathList':
          return <String, dynamic>{'list': <dynamic>[]};
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  // The platform override is reset inside the test body: the framework
  // checks foundation globals before tearDown runs.
  void iosTest(String name, Future<void> Function(WidgetTester) body) =>
      testWidgets(name, (tester) async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        try {
          await body(tester);
        } finally {
          debugDefaultTargetPlatformOverride = null;
        }
      });

  Future<void> openPicker(WidgetTester tester) async {
    await pumpApp(tester);
    tester.state<NavigatorState>(find.byType(Navigator).first).push(
        MaterialPageRoute<void>(
            builder: (_) => const PhotoPickerScreen()));
    await settle(tester);
  }

  iosTest('opening asks for no permission and offers 顯示最近照片',
      (tester) async {
    await openPicker(tester);

    expect(calls, contains('getPermissionState'));
    expect(calls, isNot(contains('requestPermissionExtend')));
    expect(find.text('顯示最近照片'), findsOneWidget);
    expect(find.text('從相簿選擇'), findsOneWidget);
  });

  iosTest('tapping 顯示最近照片 is the only place the permission is asked',
      (tester) async {
    await openPicker(tester);

    await tester.tap(find.text('顯示最近照片'));
    await settle(tester);

    expect(calls.where((c) => c == 'requestPermissionExtend').length, 1);
    expect(calls, contains('getAssetPathList'));
    expect(find.text('顯示最近照片'), findsNothing);
  });

  iosTest('a denial hides the button and is not asked again on open',
      (tester) async {
    currentState = denied;
    await openPicker(tester);

    expect(calls, isNot(contains('requestPermissionExtend')));
    expect(calls, isNot(contains('getAssetPathList')));
    expect(find.text('顯示最近照片'), findsNothing);
    expect(find.text('從相簿選擇'), findsOneWidget);
  });

  iosTest('already allowed: photos load on open without the button',
      (tester) async {
    currentState = authorized;
    await openPicker(tester);

    expect(calls, isNot(contains('requestPermissionExtend')));
    expect(calls, contains('getAssetPathList'));
    expect(find.text('顯示最近照片'), findsNothing);
  });
}
