import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

import 'helpers.dart';

Map<String, dynamic> dictionary(int version) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': '$version',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'help',
          'normalized': 'help',
          'pos': 'verb',
          'status': 'full',
          'cefr': 'A1',
          'senses': [
            {'id': 1, 'definition': 'assist', 'native': '幫助$version'}
          ],
          'relations': [
            {
              'relation': 'synonyms',
              'word': 'assist$version',
              'native': '協助$version',
              'cefr': 'A1',
            }
          ],
          'forms': [
            {
              'field': 'verb_past',
              'form': 'helped$version',
              'normalized': 'helped$version',
              'label': '過去式',
            }
          ],
          'morphemes': [
            {'part': 'help', 'kind': 'root', 'native': '幫助$version'},
            {'part': '-er', 'kind': 'suffix', 'native': '人$version'},
          ],
          'etymology': {'text': 'Old English', 'native': '古英語$version'},
        }
      ],
    };

const editedFields = {
  WordField.related,
  WordField.forms,
  WordField.morphology,
  WordField.etymology,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() => LexiconPack.instance.clear());

  for (final clear in [false, true]) {
    test(
        'HTTP update and Hive restart preserve ${clear ? 'deletions' : 'edits'}',
        () async {
      // Retain the isolated test data under app/; no existing user data is deleted.
      final dir = await Directory('build').createTemp('card31-hive-');
      Hive.init(dir.path);
      addTearDown(Hive.close);
      final store = await HiveWordDatabaseStore.open();
      var repo = WordDatabaseRepository(store: store);
      final id = repo.addWord(word: 'help', pos: 'verb', meaning: '').id;
      var version = 1;
      DictionarySync makeSync() => DictionarySync(
          client: MockClient((_) async => http.Response.bytes(
              utf8.encode(jsonEncode(dictionary(version))), 200)));
      var sync = makeSync();
      addTearDown(() => sync.dispose());
      await sync.start(AppSettings.inMemory(), () => repo);
      expect(repo.entry(id)!.forms.single.form, 'helped1');
      expect(learningEtymology(repo.entry(id)!), '古英語1');
      repo.editEntry(
          repo.entry(id)!.copyWith(
                related: clear
                    ? []
                    : const [
                        RelatedWord('aid', RelationType.synonym, native: '援助')
                      ],
                forms: clear ? [] : const [WordForm('helped', '我的過去式')],
                morphology: () => clear ? null : '我的構詞',
                etymology: () => clear ? null : '我的詞源',
              ),
          editedFields);
      await repo.flush();
      sync.dispose();
      await Hive.close();
      Hive.init(dir.path);
      final reopened = await HiveWordDatabaseStore.open();
      repo = WordDatabaseRepository.fromData(reopened.load(), store: reopened);
      sync = makeSync();
      await sync.start(AppSettings.inMemory(), () => repo);
      version = 2;
      await sync.refresh();
      final after = repo.entry(id)!;
      expect(after.meaning, '幫助2'); // Unedited fields still update.
      expect(after.userEdited, containsAll(editedFields));
      expect(after.related.map((r) => r.word), clear ? [] : ['aid']);
      expect(after.forms.map((f) => f.form), clear ? [] : ['helped']);
      expect(learningRelations(after, 'A1', 'synonyms'),
          clear ? [] : [(word: 'aid', meaning: '援助')]);
      expect(learningMorphology(after), clear ? null : '我的構詞');
      expect(learningEtymology(after), clear ? null : '我的詞源');
      expect(
          LexiconPack.instance.lookup('help')!.entry.etymology!.native, '古英語2');
      await repo.flush();
    });
  }

  test('unedited extended fields follow newer dictionary data', () {
    final repo = WordDatabaseRepository();
    final id = repo.addWord(word: 'help', pos: 'verb', meaning: '').id;
    for (final version in [1, 2]) {
      LexiconPack.instance.loadJson(dictionary(version));
      repo.linkLexicon(LexiconPack.instance);
      final e = repo.entry(id)!;
      expect(e.forms.single.form, 'helped$version');
      expect(e.related.single.native, '協助$version');
      expect(e.etymology, '古英語$version');
      expect(learningMorphology(e), contains('幫助$version'));
    }
  });

  late WordDatabaseRepository repo;
  late String id;
  (WordEntry, Set<String>)? result;
  Future<void> open(WidgetTester tester) async {
    LexiconPack.instance.loadJson(dictionary(1));
    repo = WordDatabaseRepository(clock: () => testNow);
    id = repo.addWord(word: 'help', pos: 'verb', meaning: '').id;
    repo.linkLexicon(LexiconPack.instance);
    result = null;
    await pumpApp(tester,
        repository: repo,
        home: Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () async {
                      result =
                          await showEditWordDialog(context, repo.entry(id)!);
                      if (result != null) {
                        repo.editEntry(result!.$1, result!.$2);
                      }
                    },
                    child: const Text('open')))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  Finder field(String label) => find.byWidgetPredicate(
      (w) => w is TextField && w.decoration?.labelText == label);
  Future<void> fill(WidgetTester tester, String label, String value) async {
    final target = field(label).last;
    await tester.ensureVisible(target);
    await tester.enterText(target, value);
    await tester.pump();
  }

  Future<void> tapVisible(WidgetTester tester, Finder target) async {
    await tester.ensureVisible(target);
    await tester.tap(target);
    await tester.pumpAndSettle();
  }

  testWidgets('dialog changes, adds and displays all extended overrides',
      (tester) async {
    await open(tester);
    await fill(tester, '相關單字', 'aid');
    await fill(tester, '相關字釋義', '援助');
    await tapVisible(tester, find.text('新增相關字'));
    await fill(tester, '相關單字', 'support');
    await fill(tester, '相關字釋義', '支持');
    await fill(tester, '變化形', 'helped');
    await fill(tester, '變化說明（例如：過去式）', '過去式修訂');
    await tapVisible(tester, find.text('新增詞形變化'));
    await fill(tester, '變化形', 'helping');
    await fill(tester, '變化說明（例如：過去式）', '現在分詞');
    await fill(tester, '構詞（字根、字首／字尾與解釋）', '使用者構詞');
    await fill(tester, '詞源', '使用者詞源');
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(result!.$2, editedFields);
    final e = repo.entry(id)!;
    expect(e.related.map((r) => r.word), ['aid', 'support']);
    expect(e.forms.map((f) => f.form), ['helped', 'helping']);
    expect(learningMorphology(e), '使用者構詞');
    expect(learningEtymology(e), '使用者詞源');
    await pumpApp(tester,
        repository: repo, home: WordDetailScreen(wordEntryId: id));
    expect(find.text('更多單字資訊'), findsNothing);
    expect(find.text('學習資訊'), findsNothing);
    expect(find.text('使用者構詞'), findsOneWidget);
    expect(find.text('使用者詞源'), findsOneWidget);
    expect(find.textContaining('aid'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'relation type changes stay distinct; untouched fields still update',
      (tester) async {
    await open(tester);
    final dropdown = find.byType(DropdownButtonFormField<RelationType>);
    await tapVisible(tester, dropdown);
    await tester.tap(find.text('反義字').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(result!.$2, {WordField.related});
    LexiconPack.instance.loadJson(dictionary(2));
    repo.linkLexicon(LexiconPack.instance);
    final e = repo.entry(id)!;
    expect(learningRelations(e, 'A1', 'synonyms'), isEmpty);
    expect(learningRelations(e, 'A1', 'antonyms').single.word, 'assist1');
    expect(e.forms.single.form, 'helped2');
    expect(learningEtymology(e), '古英語2');
    expect(learningMorphology(e), contains('幫助2'));
  });

  testWidgets('dialog can delete every extended field', (tester) async {
    await open(tester);
    await tapVisible(tester, find.byTooltip('刪除相關字'));
    await tapVisible(tester, find.byTooltip('刪除詞形變化'));
    await fill(tester, '構詞（字根、字首／字尾與解釋）', '');
    await fill(tester, '詞源', '');
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(result!.$2, editedFields);
    LexiconPack.instance.loadJson(dictionary(2));
    repo.linkLexicon(LexiconPack.instance);
    final e = repo.entry(id)!;
    expect(e.related, isEmpty);
    expect(e.forms, isEmpty);
    expect(learningMorphology(e), isNull);
    expect(learningEtymology(e), isNull);
  });

  testWidgets('unchanged save and cancel do not mark overrides',
      (tester) async {
    await open(tester);
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(result, isNull);
    expect(repo.entry(id)!.userEdited, isEmpty);
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await fill(tester, '詞源', '尚未儲存');
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(result, isNull);
    expect(repo.entry(id)!.userEdited, isEmpty);
  });

  testWidgets('empty new rows require input or deletion', (tester) async {
    await open(tester);
    await tapVisible(tester, find.text('新增相關字'));
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(find.text('請填寫或刪除此列'), findsOneWidget);
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(repo.entry(id)!.userEdited, isEmpty);
  });
}
