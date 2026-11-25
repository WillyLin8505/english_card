import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:google_sign_in_web/web_only.dart' as web;

import 'social_sign_in.dart' show SocialCredential;

bool _initialised = false;
StreamSubscription<GoogleSignInAuthenticationEvent>? _sub;

/// Google Identity Services button (card #1271): the web plugin cannot
/// `authenticate()`, it renders Google's own button and reports the ID token
/// through `authenticationEvents`.
Widget? buildGoogleWebButton(
    String clientId, void Function(SocialCredential) onCredential) {
  return FutureBuilder<void>(
    future: _init(clientId, onCredential),
    builder: (context, snap) => snap.connectionState == ConnectionState.done
        ? SizedBox(
            height: 44,
            child: web.renderButton(
                configuration: web.GSIButtonConfiguration(
                    type: web.GSIButtonType.standard,
                    text: web.GSIButtonText.continueWith,
                    size: web.GSIButtonSize.large)))
        : const SizedBox(height: 44, width: 200),
  );
}

Future<void> _init(
    String clientId, void Function(SocialCredential) onCredential) async {
  if (!_initialised) {
    await GoogleSignIn.instance.initialize(clientId: clientId);
    _initialised = true;
  }
  await _sub?.cancel();
  _sub = GoogleSignIn.instance.authenticationEvents.listen((e) {
    if (e is GoogleSignInAuthenticationEventSignIn) {
      final id = e.user.authentication.idToken;
      if (id != null) onCredential(SocialCredential(id, e.user.displayName));
    }
  });
}
