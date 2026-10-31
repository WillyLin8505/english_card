import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

/// An ID token from Google / Apple, plus the name they shared the first time.
class SocialCredential {
  final String token;
  final String? name;
  const SocialCredential(this.token, [this.name]);
}

/// Google and Apple sign-in behind one seam so tests (and a build without a
/// Client ID) never touch the platform plugins. A null result = the learner
/// closed the sheet.
abstract class SocialSignIn {
  bool get googleConfigured;
  bool get appleAvailable;
  Future<SocialCredential?> google();
  Future<SocialCredential?> apple();
}

class PlatformSocialSignIn implements SocialSignIn {
  /// OAuth client IDs come from `--dart-define` (never in git): the iOS client
  /// and the web/server client whose ID the backend checks as `aud`.
  static const googleClientId = String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
  static const googleServerClientId =
      String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');

  static bool _googleReady = false;

  @override
  bool get googleConfigured =>
      !kIsWeb && (googleClientId.isNotEmpty || googleServerClientId.isNotEmpty);

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
      return SocialCredential(id, name.isEmpty ? null : name);
    } on SignInWithAppleAuthorizationException catch (e) {
      if (e.code == AuthorizationErrorCode.canceled) return null;
      rethrow;
    }
  }
}
