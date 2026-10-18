import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/license_links.dart';

void main() {
  test('Creative Commons names map to their license pages', () {
    expect(licenseUrlFor('CC BY-SA 4.0'),
        'https://creativecommons.org/licenses/by-sa/4.0/');
    expect(licenseUrlFor('CC BY 3.0 US'),
        'https://creativecommons.org/licenses/by/3.0/us/');
    expect(licenseUrlFor('CC BY 2.0 FR'),
        'https://creativecommons.org/licenses/by/2.0/fr/');
    expect(licenseUrlFor('CC0'),
        'https://creativecommons.org/publicdomain/zero/1.0/');
  });

  test('no license page for public domain, BSD or unknown names', () {
    expect(licenseUrlFor('Public domain'), isNull);
    expect(licenseUrlFor('BSD-2-Clause'), isNull);
    expect(licenseUrlFor(null), isNull);
  });
}
