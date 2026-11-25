// Owner 11/25 desktop simulation: on the web, Dart ints are JavaScript numbers
// and `<<` works on 32 bits, so `1 << 40` is 0. `clamp(1000, 1 << 40)` then
// threw after every recognition (web photos all failed) and crashed the
// progress line to a grey page. VM tests can't see it, so scan the source.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('no shift by 31 or more in lib/ (it is 0 or negative on the web)', () {
    final bad = <String>[];
    final shift = RegExp(r'<<\s*(3[1-9]|[4-9]\d)\b');
    for (final f in Directory('lib').listSync(recursive: true)) {
      if (f is! File || !f.path.endsWith('.dart')) continue;
      final lines = f.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final code = lines[i].split('//').first;
        if (shift.hasMatch(code)) bad.add('${f.path}:${i + 1}: ${lines[i].trim()}');
      }
    }
    expect(bad, isEmpty);
  });
}
