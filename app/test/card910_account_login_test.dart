import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/cloud_backup.dart';
import 'package:photo_english_app/services/cloud_token_store.dart';
import 'package:photo_english_app/services/social_sign_in.dart';
import 'package:photo_english_app/widgets/account_sign_in.dart';

class _Social implements SocialSignIn {
  @override
  bool googleConfigured = true;
  @override
  bool appleAvailable = true;
  @override
  Future<SocialCredential?> google() async =>
      const SocialCredential('g-token', 'Gina');
  @override
  Future<SocialCredential?> apple() async => null; // learner closed the sheet
}

void main() {
  test('the account server is fixed and not the tagging URL', () {
    final cloud = CloudBackup(AppSettings.inMemory(taggingUrl: 'http://dev'));
    expect(cloud.available, isTrue);
    expect(cloud.baseUrl, CloudBackup.accountUrl);
    expect(CloudBackup.accountUrl, startsWith('https://'));
  });

  test('Google, Apple login and delete account call the server', () async {
    final seen = <String>[];
    final client = MockClient((req) async {
      seen.add('${req.method} ${req.url.path} ${req.body}');
      if (req.url.path.endsWith('/delete')) {
        return http.Response(jsonEncode({'ok': true}), 200);
      }
      return http.Response(
          jsonEncode({
            'token': 'tok',
            'user': {'email': 'gina@gmail.com', 'nickname': 'Gina'}
          }),
          200);
    });
    final settings = AppSettings.inMemory();
    final cloud =
        CloudBackup(settings, client: client, baseUrl: 'https://x.test');
    await cloud.loginWithGoogle('g-token', name: 'Gina');
    expect(seen.last, contains('/api/account/google'));
    expect(seen.last, contains('"id_token":"g-token"'));
    expect(settings.cloudEmail, 'gina@gmail.com');
    await cloud.loginWithApple('a-token');
    expect(seen.last, contains('/api/account/apple'));
    expect(seen.last, contains('"identity_token":"a-token"'));
    await cloud.deleteAccount();
    expect(seen.last, startsWith('POST /api/account/delete'));
    expect(settings.cloudSignedIn, isFalse);
  });

  test('the token goes to the Keychain store, never the settings box',
      () async {
    final store = MemoryTokenStore();
    final settings = AppSettings.inMemory();
    settings.attachTokenStoreForTest(store);
    settings.setCloudAccount('secret', 'a@x.com');
    await Future<void>.delayed(Duration.zero);
    expect(store.value, 'secret');
    settings.setCloudAccount('', '');
    await Future<void>.delayed(Duration.zero);
    expect(store.value, '');
  });

  testWidgets('sign-in buttons: Google signs in, Apple cancel does nothing',
      (tester) async {
    final settings = AppSettings.inMemory();
    final client = MockClient((req) async => http.Response(
        jsonEncode({
          'token': 'tok',
          'user': {'email': 'gina@gmail.com'}
        }),
        200));
    var signedIn = 0;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AccountSignInButtons(
                settings: settings,
                social: _Social(),
                cloud: CloudBackup(settings,
                    client: client, baseUrl: 'https://x.test'),
                onSignedIn: () => signedIn++))));
    expect(find.byKey(const Key('signInApple')), findsOneWidget);
    await tester.tap(find.byKey(const Key('signInApple')));
    await tester.pumpAndSettle();
    expect(settings.cloudSignedIn, isFalse);
    await tester.tap(find.byKey(const Key('signInGoogle')));
    await tester.pumpAndSettle();
    expect(settings.cloudSignedIn, isTrue);
    expect(signedIn, 1);
  });

  testWidgets('no Google or Apple button without a Client ID / on Android',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AccountSignInButtons(
                settings: AppSettings.inMemory(),
                social: _Social()
                  ..googleConfigured = false
                  ..appleAvailable = false))));
    expect(find.byKey(const Key('signInGoogle')), findsNothing);
    expect(find.byKey(const Key('signInApple')), findsNothing);
    expect(find.byKey(const Key('signInEmail')), findsOneWidget);
  });
}
