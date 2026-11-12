import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/app_settings.dart';

// Card #1006: the store build (store.json, no TAGGING_URL / DEV_TOOLS) must
// recognize photos on the device and show no server fields.
void main() {
  test('store build: local recognition, no server UI, no dev upload', () {
    expect(AppSettings.defaultTaggingUrl, isEmpty);
    expect(AppSettings.developerTools, isFalse);
    final saved = AppSettings.localRecognition;
    addTearDown(() => AppSettings.localRecognition = saved);
    AppSettings.localRecognition = true;
    final settings = AppSettings.inMemory();
    expect(settings.usesLocalRecognition, isTrue);
    expect(settings.showsTaggingServer, isFalse);
  });
}
