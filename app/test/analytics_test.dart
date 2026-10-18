import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/analytics.dart';

void main() {
  tearDown(() {
    final a = Analytics.instance;
    a.sharing = false;
    a.debugTreatAsEnabled = false;
  });

  test('without POSTHOG_API_KEY analytics is off and never throws', () async {
    final a = Analytics.instance;
    expect(a.enabled, isFalse);
    expect(a.sharing, isFalse);
    await a.start();
    a.capture('card_reviewed', {'rating': 'good'});
    a.screen('album');
    await a.flush();
    expect(a.pendingCount, 0);
  });

  test('events stay queued only while sharing is on', () {
    final a = Analytics.instance;
    a.debugTreatAsEnabled = true;
    a.sharing = false;
    a.capture('app_opened');
    expect(a.pendingCount, 0);
    a.sharing = true;
    a.capture('card_reviewed', {'rating': 'good'});
    expect(a.pendingCount, 1);
    a.sharing = false;
    expect(a.pendingCount, 0);
  });
}
