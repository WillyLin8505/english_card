import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/speaker.dart';

import 'helpers.dart';

/// 問題回報 #176: a speaker that cannot make a sound used to fail silently
/// (only a debugPrint). It should now tell the learner.
class _FailingSpeaker implements Speaker {
  String? lastAccent;

  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    lastAccent = accent;
    return false;
  }

  @override
  Future<void> stop() async {}
}

void main() {
  testWidgets('a speaker that cannot play anything shows a toast', (tester) async {
    final speaker = _FailingSpeaker();
    final app = await pumpApp(tester, speaker: speaker);
    app.navigator.openWord('w-balcony');
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('播放發音').first);
    await tester.pump();
    expect(find.textContaining('播放發音失敗'), findsOneWidget);
  });

  testWidgets('the chosen English accent reaches the speaker', (tester) async {
    final speaker = _FailingSpeaker();
    final settings = AppSettings.inMemory(englishAccent: 'en-US');
    final app = await pumpApp(tester, speaker: speaker, settings: settings);
    app.navigator.openWord('w-balcony');
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('播放發音').first);
    await tester.pump();
    expect(speaker.lastAccent, 'en-US');
  });

  testWidgets('設定 lets the learner switch 英式/美式', (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.settings);
    expect(app.settings.englishAccent, 'en-GB');

    await tester.tap(find.text('美式（en-US）'));
    await tester.pump();
    expect(app.settings.englishAccent, 'en-US');
  });
}
