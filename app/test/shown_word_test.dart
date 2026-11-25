// 問題回報 #499 (卡 #496): photo labels, exercise options and the camera
// show a word as the card back does — French keeps its lowercase spelling.
// 問題回報 #1770: English is lowercase too (plant, not Plant).
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('English is lowercase headword, French keeps its spelling', () {
    expect(shownWord('cutting board', 'en'), 'cutting board');
    expect(shownWord('plant', 'en', pos: 'noun'), 'plant');
    expect(shownWord('pomme', 'fr', pos: 'noun'), 'pomme');
    expect(shownWord('manger', 'fr', pos: 'verb'), 'manger');
    expect(shownWord('pomme', 'fr'), 'pomme');
  });
}
