// Card #1220 / 問題回報 #1672: the French word page — article + gender,
// conjugation tables, adjective grid, h aspiré. aller, parler, se lever,
// maison, beau, héros.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/french_detail.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

Map<String, dynamic> _f(String field, String form) =>
    {'field': field, 'form': form, 'normalized': form};

List<Map<String, dynamic>> _tense(String t, List<String> v,
        [List<String> persons = const ['1s', '2s', '3s', '1p', '2p', '3p']]) =>
    [for (var i = 0; i < persons.length; i++) _f('fr_${t}_${persons[i]}', v[i])];

Map<String, dynamic> _lex(int id, String lemma, String pos, String native,
        List<Map<String, dynamic>> forms) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': pos,
      'status': 'full',
      'cefr': 'A1',
      'senses': [
        {'id': id * 10, 'definition': 'd', 'native': native}
      ],
      'forms': forms,
    };

Map<String, dynamic> _pack() => {
      'catalog_version': 1,
      'schema_version': 4,
      'target_language': 'fr',
      'native_language': 'en',
      'lexemes': [
        _lex(1, 'aller', 'verb', 'to go', [
          ..._tense('present', ['vais', 'vas', 'va', 'allons', 'allez', 'vont']),
          ..._tense('imperfect',
              ['allais', 'allais', 'allait', 'allions', 'alliez', 'allaient']),
          ..._tense('future', ['irai', 'iras', 'ira', 'irons', 'irez', 'iront']),
          ..._tense('subjunctive',
              ['aille', 'ailles', 'aille', 'allions', 'alliez', 'aillent']),
          ..._tense('imperative', ['va', 'allons', 'allez'], ['2s', '1p', '2p']),
          _f('fr_auxiliary', 'être'),
          _f('fr_past_participle', 'allé'),
          _f('fr_present_participle', 'allant'),
        ]),
        _lex(2, 'parler', 'verb', 'to speak', [
          ..._tense('present',
              ['parle', 'parles', 'parle', 'parlons', 'parlez', 'parlent']),
          ..._tense('future', [
            'parlerai',
            'parleras',
            'parlera',
            'parlerons',
            'parlerez',
            'parleront'
          ]),
          _f('fr_auxiliary', 'avoir'),
          _f('fr_past_participle', 'parlé'),
        ]),
        _lex(3, 'se lever', 'verb', 'to get up', [
          ..._tense('present',
              ['lève', 'lèves', 'lève', 'levons', 'levez', 'lèvent']),
          _f('fr_auxiliary', 'être'),
          _f('fr_past_participle', 'levé'),
        ]),
        _lex(4, 'maison', 'noun', 'house',
            [_f('fr_gender', 'f'), _f('fr_plural', 'maisons')]),
        _lex(5, 'beau', 'adj', 'beautiful', [
          _f('fr_feminine', 'belle'),
          _f('fr_plural', 'beaux'),
          _f('fr_feminine_plural', 'belles'),
          _f('fr_masculine_before_vowel', 'bel'),
        ]),
        _lex(6, 'héros', 'noun', 'hero',
            [_f('fr_gender', 'm'), _f('fr_h_aspire', '1')]),
        _lex(7, 'arbre', 'noun', 'tree', [_f('fr_gender', 'm')]),
        _lex(8, 'chat', 'noun', 'cat', []),
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(_pack()));
  tearDown(() => LexiconPack.instance.clear());

  Future<void> open(WidgetTester tester, int id) async {
    await pumpApp(tester,
        settings:
            AppSettings.inMemory(nativeLanguage: 'en', learningLanguage: 'fr'),
        home: DatabaseWordScreen(wordId: id),
        size: const Size(402, 1800));
    await tester.pumpAndSettle();
  }

  testWidgets('aller: être, irregular, passé composé built', (t) async {
    await open(t, 1);
    expect(find.text('Conjugation'), findsOneWidget);
    expect(find.textContaining('auxiliary être'), findsOneWidget);
    expect(find.textContaining('irregular verb'), findsOneWidget);
    expect(find.text('je vais'), findsOneWidget);
    expect(find.text('je suis allé(e)'), findsOneWidget);
    expect(find.text('ils／elles sont allé(e)s'), findsOneWidget);
    // Other moods wait behind the button.
    expect(find.byKey(const ValueKey('fr-tense-subjunctive')), findsNothing);
    await t.ensureVisible(find.byKey(const ValueKey('fr-more-tenses')));
    await t.tap(find.byKey(const ValueKey('fr-more-tenses')));
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('fr-tense-subjunctive')), findsOneWidget);
    expect(find.text('allons'), findsOneWidget); // imperative, no pronoun
    expect(find.textContaining('fr_'), findsNothing); // no raw codes
  });

  testWidgets('parler: regular -er, avoir', (t) async {
    await open(t, 2);
    expect(find.textContaining('-er'), findsOneWidget);
    expect(find.textContaining('irregular verb'), findsNothing);
    expect(find.text('tu as parlé'), findsOneWidget);
    expect(find.text('je parle'), findsOneWidget);
    expect(find.text('nous parlerons'), findsOneWidget);
  });

  testWidgets('se lever: pronominal, me suis levé(e)', (t) async {
    await open(t, 3);
    expect(find.textContaining('pronominal verb'), findsOneWidget);
    expect(find.text('je me lève'), findsOneWidget);
    expect(find.text('je me suis levé(e)'), findsOneWidget);
    expect(find.text('nous nous sommes levé(e)s'), findsOneWidget);
  });

  testWidgets('maison: la maison, f., plural', (t) async {
    await open(t, 4);
    expect(find.text('la maison'), findsOneWidget);
    expect(find.text('f.'), findsOneWidget);
    expect(find.text('maisons'), findsOneWidget);
    expect(find.byKey(const ValueKey('fr-verb')), findsNothing);
  });

  testWidgets('beau: 2x2 grid with bel', (t) async {
    await open(t, 5);
    expect(find.byKey(const ValueKey('fr-adjective')), findsOneWidget);
    for (final f in ['beau', 'belle', 'beaux', 'belles', 'bel']) {
      expect(find.text(f), f == 'beau' ? findsNWidgets(2) : findsOneWidget,
          reason: f);
    }
  });

  testWidgets('héros: le héros with h aspiré note; arbre: l’arbre',
      (t) async {
    await open(t, 6);
    expect(find.text('le héros'), findsOneWidget);
    expect(find.byKey(const ValueKey('fr-h-aspire')), findsOneWidget);
    await open(t, 7);
    expect(find.text("l'arbre"), findsOneWidget);
    expect(find.text('m.'), findsOneWidget);
    expect(find.byKey(const ValueKey('fr-h-aspire')), findsNothing);
  });

  testWidgets('no data, no empty shell', (t) async {
    await open(t, 8);
    expect(find.byKey(const ValueKey('fr-title')), findsNothing);
    expect(find.byKey(const ValueKey('fr-verb')), findsNothing);
  });

  test('model: no stored forms → null; article rules', () {
    expect(frenchVerbFrom('parler', const []), isNull);
    expect(frenchDefiniteArticle('homme', 'm', hAspire: false), "l'homme");
    expect(frenchDefiniteArticle('homme', 'm'), isNull);
  });

  test('card 1240: pack field fr_passe_simple_* fills the simple past table', () {
    const persons = ['1s', '2s', '3s', '1p', '2p', '3p'];
    const vals = ['parlai', 'parlas', 'parla', 'parlâmes', 'parlâtes', 'parlèrent'];
    final forms = [
      const LexForm('fr_present_1s', 'parle', 'parle', null),
      for (var i = 0; i < 6; i++)
        LexForm('fr_passe_simple_${persons[i]}', vals[i], vals[i], null),
    ];
    final v = frenchVerbFrom('parler', forms)!;
    final t = v.tables.firstWhere((x) => x.tense.code == 'simple_past');
    expect(t.cells.length, 6);
  });
}
