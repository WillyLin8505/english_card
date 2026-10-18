import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/analytics.dart';

void main() {
  test('without POSTHOG_API_KEY analytics is off and never throws', () async {
    final a = Analytics.instance;
    expect(a.enabled, isFalse);
    await a.start();
    a.capture('card_reviewed', {'rating': 'good'});
    a.screen('album');
    await a.flush();
  });
}
