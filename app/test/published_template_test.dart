import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/template_items.dart';

void main() {
  test('published order and settings survive pack load and local persistence',
      () {
    final pack = LexiconPack()
      ..loadJson({
        'lexemes': [],
        'card_template': {
          'id': '1',
          'name': 'shared',
          'version': 3,
          'layout': {
            'schema_version': 1,
            'sections': [
              {
                'key': 'examples',
                'side': 'back',
                'visible': true,
                'limit': 2,
                'collapsed': true,
                'expand_all': false
              },
              {
                'key': 'senses',
                'side': 'back',
                'visible': false,
                'limit': 1,
                'collapsed': false,
                'expand_all': true
              },
            ]
          }
        }
      });
    final restored = CardTemplate.fromJson(pack.cardTemplate!.toJson());
    expect(restored.backFields.first.field, CardBackField.example);
    expect(restored.backFields.first.limit, 2);
    expect(restored.backFields.first.collapsed, true);
    expect(restored.backFields.first.expandAll, false);
    expect(restored.backFields[1].visible, false);
    expect(restored.backFields.length, 2);
    expect(restored.publishedLayout, isNotNull);
    pack.clear();
    expect(pack.cardTemplate, isNull);
  });
  testWidgets('item limit and expand-all are applied', (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: TemplateItems(
      settings: TemplateField(CardBackField.example, limit: 1),
      children: [Text('one'), Text('two')],
    ))));
    expect(find.text('one'), findsOneWidget);
    expect(find.text('two'), findsNothing);
    await tester.tap(find.text('顯示全部'));
    await tester.pump();
    expect(find.text('two'), findsOneWidget);
  });
}
