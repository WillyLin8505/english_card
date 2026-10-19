import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/photo_intake.dart';

/// The old 64-bit FNV-1a (VM only): saved photo hashes must not change.
String _fnv64(Uint8List bytes) {
  var h = 0xcbf29ce484222325;
  for (final b in bytes) {
    h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF;
  }
  return '${bytes.length}-${h.toRadixString(16)}';
}

void main() {
  test('web-safe photo hash equals the old 64-bit FNV-1a', () {
    final r = Random(7);
    for (final n in [0, 1, 2, 7, 64, 1000, 5000]) {
      final bytes = Uint8List.fromList(List.generate(n, (_) => r.nextInt(256)));
      expect(PhotoIntake.hashBytes(bytes), _fnv64(bytes), reason: 'length $n');
    }
  });
}
