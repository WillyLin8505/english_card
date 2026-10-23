// Card 225 round 160: 517 database labels on 124 photos have point (0, 0),
// the tagger's "don't know"; they drew a pile of pins in the top-left corner
// (47 photos had every pin there). Without a box they count as no point.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';

void main() {
  test('(0, 0) without a box is no point', () {
    expect(databaseLabelPoint({'point': [0, 0]}), isNull);
    expect(databaseLabelPoint({'point': [0.0, 0.0]}), isNull);
    expect(databaseLabelPoint({}), isNull);
  });

  test('(0, 0) and (0.5, 0.5) with a box go to the box centre', () {
    expect(
        databaseLabelPoint({
          'point': [0, 0],
          'box': [0.2, 0.4, 0.6, 0.6]
        }),
        (0.4, 0.5));
    expect(
        databaseLabelPoint({
          'point': [0.5, 0.5],
          'box': [0.0, 0.0, 0.2, 0.2]
        }),
        (0.1, 0.1));
  });

  test('other points stay where they are', () {
    expect(databaseLabelPoint({'point': [0.0, 0.3]}), (0.0, 0.3));
    expect(
        databaseLabelPoint({
          'point': [0.7, 0.2],
          'box': [0.0, 0.0, 1.0, 1.0]
        }),
        (0.7, 0.2));
  });
}
