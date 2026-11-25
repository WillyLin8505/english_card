import 'package:flutter/widgets.dart';

import 'social_sign_in.dart' show SocialCredential;

/// Non-web builds have no Google Identity Services button.
Widget? buildGoogleWebButton(
        String clientId, void Function(SocialCredential) onCredential) =>
    null;
