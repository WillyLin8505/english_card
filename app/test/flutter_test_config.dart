import 'dart:async';

import 'package:photo_english_app/theme/mobile_theme.dart';

/// Runs before every test file: tests never download fonts.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  MFont.useGoogleFonts = false;
  await testMain();
}
