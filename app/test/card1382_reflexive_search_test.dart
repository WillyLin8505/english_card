import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/word_database_query.dart';

void main() {
  test('card #1382: reflexive prefix is stripped', () {
    expect(reflexiveBare('se lever'), 'lever');
    expect(reflexiveBare("S'asseoir"), 'asseoir');
    expect(reflexiveBare('serpent'), isNull);
    expect(reflexiveBare('se'), isNull);
  });
}
