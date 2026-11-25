// Card #1291 / 問題回報 #1697: the 詞形變化 chips of a French word must show
// an aspirated h as its label only (有聲 h（h aspiré）), never the raw value.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _f(String field, String form) =>
    {'field': field, 'form': form, 'normalized': form};

Map<String, dynamic> _pack() => {
      'catalog_version': 1,
      'schema_version': 4,
      'target_language': 'fr',
      'native_language': 'en',
      'lexemes': [
        {
          'id': 6,
          'lemma': 'héros',
          'normalized': 'héros',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'senses': [
            {'id': 60, 'definition': 'hero', 'native': 'héros'}
          ],
          'forms': [_f('fr_gender', 'm'), _f('fr_h_aspire', 'yes')],
        },
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(_pack()));
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('wordbook page: aspirated h chip shows the label, not the value',
      (t) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: 'héros', pos: 'noun', meaning: '').id;
    repo.linkLexicon(LexiconPack.instance);
    await pumpApp(t,
        repository: repo,
        settings:
            AppSettings.inMemory(nativeLanguage: 'en', learningLanguage: 'fr'),
        home: WordDetailScreen(wordEntryId: id),
        size: const Size(402, 1800));
    await t.pumpAndSettle();
    expect(find.text('aspirated h (h aspiré)'), findsOneWidget);
    expect(find.textContaining('yes'), findsNothing);
  });
}
