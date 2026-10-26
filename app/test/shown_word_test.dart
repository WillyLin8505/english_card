// 問題回報 #499 (卡 #496): photo labels, exercise options and the camera
// show a word as the card back does — French keeps its lowercase spelling.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('English is capitalised, French keeps its spelling', () {
    expect(shownWord('cutting board', 'en'), 'Cutting Board');
    expect(shownWord('pomme', 'fr', pos: 'noun'), 'pomme');
    expect(shownWord('manger', 'fr', pos: 'verb'), 'manger');
    expect(shownWord('pomme', 'fr'), 'pomme');
  });
}
