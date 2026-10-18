import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

LexiconPack phrasePack() => LexiconPack()..loadJson({
  'target_language': 'en', 'native_language': 'zh-TW',
  'lexemes': [{
    'id': 20, 'lemma': 'turn off', 'normalized': 'turn off',
    'pos': 'verb', 'entry_type': 'phrasal_verb', 'cefr': 'A1',
    'senses': [{'id': 200, 'native': '關閉', 'definition': 'stop a device'}],
    'examples': [{'text': 'Please turn off the light.', 'translation': '請關燈。', 'level': 'A1', 'sense_id': 200}],
  }],
});

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('old data defaults to word; sync and persistence retain type and usages', () {
    final repo = WordDatabaseRepository();
    final old = repo.addWord(word: 'turn off', pos: 'verb', meaning: '關閉');
    final json = old.toJson()..remove('entry_type');
    expect(WordEntry.fromJson(json).entryType, 'word');
    expect(LexEntry.fromJson({'id': 1, 'lemma': 'old', 'normalized': 'old', 'pos': 'adj'}).entryType, 'word');
    repo.linkLexicon(phrasePack());
    final entry = repo.entry(old.id)!;
    expect(entry.entryType, 'phrasal_verb');
    expect(entry.usages, isNotEmpty);
    expect(WordEntry.fromJson(entry.toJson()).copyWith(meaning: '關掉').entryType, 'phrasal_verb');
    expect(repo.linkLexicon(phrasePack()), 0);
    repo.dispose();
  });

  test('new entries use dictionary type and localized labels', () {
    final repo = WordDatabaseRepository()..linkLexicon(phrasePack());
    expect(repo.addWord(word: 'turn off', pos: 'verb', meaning: '關閉').entryType, 'phrasal_verb');
    expect(entryTypeLabel('word'), '');
    expect(entryTypeLabel('phrase'), '片語');
    expect(entryTypeLabel('idiom'), '慣用語');
    expect(entryTypeLabel('collocation'), '搭配詞');
    expect(entryTypeLabel('fixed_expression'), '固定表達');
    expect(entryTypeLabel('future_type'), '片語');
    LexiconPack.instance.labels['entry_type:idiom'] = 'Idiom';
    expect(entryTypeLabel('idiom'), 'Idiom');
    repo.dispose();
  });

  testWidgets('photo label includes type and fits narrow layout', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: WordPin(
      word: 'turn off', zh: '關閉', entryType: 'phrasal_verb', maxWidth: 100,
    ))));
    expect(find.text('[片語動詞] 關閉'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('word list and card answer show phrase type', (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addWord(word: 'turn off', pos: 'verb', meaning: '關閉');
    repo.linkLexicon(phrasePack());
    final app = await pumpApp(tester, repository: repo, initialTab: AppTab.words);
    expect(find.text('片語動詞・動詞'), findsOneWidget);
    app.navigator.selectTab(AppTab.review);
    await tester.pumpAndSettle();
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'turn off');
    await tester.tap(find.byTooltip('送出答案'));
    await tester.pumpAndSettle();
    expect(find.text('片語動詞'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
