import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void main() {
  test('a word added with a meaning is marked with the pack native (#1723)', () {
    final pack = LexiconPack.instance;
    final old = pack.native;
    addTearDown(() => pack.native = old);
    pack.native = 'en';
    final repo = testRepository();
    final e = repo.addWord(word: 'bicyclettetest', pos: 'noun', meaning: 'bicycle');
    expect(e.translatedFor, 'en');
    expect(e.nativeOfData, 'en');
  });
}
