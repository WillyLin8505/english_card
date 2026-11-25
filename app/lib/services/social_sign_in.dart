import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/widgets.dart' show Widget;
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import 'google_web_button_stub.dart'
    if (dart.library.js_interop) 'google_web_button.dart';

/// An ID token from Google / Apple, plus the name they shared the first time.
class SocialCredential {
  final String token;
  final String? name;

  /// Apple's one-time authorizationCode: the server swaps it for a refresh
  /// token so deleting the account can revoke the Apple grant (5.1.1(v)).
  final String? authorizationCode;
  const SocialCredential(this.token, [this.name, this.authorizationCode]);
}

/// Google and Apple sign-in behind one seam so tests (and a build without a
/// Client ID) never touch the platform plugins. A null result = the learner
/// closed the sheet.
abstract class SocialSignIn {
  bool get googleConfigured;
  bool get appleAvailable;
  Future<SocialCredential?> google();
  Future<SocialCredential?> apple();

  /// Web only: Google's own sign-in button; null elsewhere. The credential
  /// arrives through [onCredential] when the learner picks an account.
  Widget? googleWebButton(void Function(SocialCredential) onCredential);

  /// Revokes the Google grant on sign-out / account deletion (5.1.1(v)).
  Future<void> googleDisconnect();
}

class PlatformSocialSignIn implements SocialSignIn {
  /// OAuth client IDs come from `--dart-define` (never in git): the iOS client
  /// and the web/server client whose ID the backend checks as `aud`.
  static const googleClientId = String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
  static const googleServerClientId =
      String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');

  /// Web OAuth client ID (`--dart-define=GOOGLE_WEB_CLIENT_ID=...`, authorised
  /// origins https://api.willylinai.com and http://127.0.0.1:8123).
  static const googleWebClientId = String.fromEnvironment('GOOGLE_WEB_CLIENT_ID');

  static bool _googleReady = false;

  @override
  bool get googleConfigured => kIsWeb
      ? googleWebClientId.isNotEmpty
      : (googleClientId.isNotEmpty || googleServerClientId.isNotEmpty);

  @override
  Widget? googleWebButton(void Function(SocialCredential) onCredential) =>
      kIsWeb && googleWebClientId.isNotEmpty
          ? buildGoogleWebButton(googleWebClientId, onCredential)
          : null;

  /// Apple's button is required next to Google on iOS (App Review 4.8).
  @override
  bool get appleAvailable => !kIsWeb && (Platform.isIOS || Platform.isMacOS);

  @override
  Future<SocialCredential?> google() async {
    final g = GoogleSignIn.instance;
    if (!_googleReady) {
      await g.initialize(
          clientId: googleClientId.isEmpty ? null : googleClientId,
          serverClientId:
              googleServerClientId.isEmpty ? null : googleServerClientId);
      _googleReady = true;
    }
    try {
      final account = await g.authenticate();
      final id = account.authentication.idToken;
      if (id == null) return null;
      return SocialCredential(id, account.displayName);
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) return null;
      rethrow;
    }
  }

  @override
  Future<void> googleDisconnect() async {
    if (!_googleReady) return; // never signed in with Google in this run
    try {
      await GoogleSignIn.instance.disconnect();
    } catch (_) {} // sign-out / deletion must not fail on this
  }

  @override
  Future<SocialCredential?> apple() async {
    try {
      final c = await SignInWithApple.getAppleIDCredential(scopes: [
        AppleIDAuthorizationScopes.email,
        AppleIDAuthorizationScopes.fullName,
      ]);
      final id = c.identityToken;
      if (id == null) return null;
      final name = [c.givenName, c.familyName]
          .whereType<String>()
          .where((s) => s.isNotEmpty)
          .join(' ');
      return SocialCredential(
          id, name.isEmpty ? null : name, c.authorizationCode);
    } on SignInWithAppleAuthorizationException catch (e) {
      if (e.code == AuthorizationErrorCode.canceled) return null;
      rethrow;
    }
  }
}
