import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/bulk_add_words.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/bulk_add_dialog.dart';

import 'helpers.dart';

Map<String, dynamic> lex(int id, String w, String pos, String cefr, String zh,
        {List<String> forms = const []}) =>
    {
      'id': id,
      'lemma': w,
      'normalized': w,
      'pos': pos,
      'cefr': cefr,
      'status': 'full',
      'senses': [
        {'id': id * 10, 'native': zh, 'definition': 'd'}
      ],
      'forms': [
        for (final f in forms)
          {'field': 'form', 'form': f, 'normalized': f, 'label': 'x'}
      ],
    };

LexiconPack pack() => LexiconPack()
  ..loadJson({
    'schema_version': 3,
    'target_language': 'en',
    'native_language': 'zh-TW',
    'lexemes': [
      lex(1, 'brew', 'verb', 'B2', '釀造', forms: ['brewed', 'brewing']),
      lex(2, 'dog', 'noun', 'A1', '狗'),
      lex(3, 'balcony', 'noun', 'B1', '陽台'),
      lex(4, 'pick up', 'phrase', 'A2', '撿起'),
    ],
  });

WordDatabaseRepository repo() {
  final r = WordDatabaseRepository(clock: () => testNow);
  r.addWord(word: 'dog', pos: 'noun', meaning: '狗');
  return r;
}

BulkItem one(String w) => classifyBulkWord(w, repo(), pack());

void main() {
  test('splits on lines, commas, 、, tabs; drops blanks and repeats', () {
    expect(
        splitBulkWords('Dog\n dog ,Cat、bird\tfish，  \n\nPick   Up;x'),
        ['dog', 'cat', 'bird', 'fish', 'pick up', 'x']);
  });

  test('each word gets its status', () {
    expect(one('balcony').status, BulkStatus.ready);
    expect(one('balcony').meaning, '陽台');
    expect(one('balcony').level, 'B1');
    expect(one('dog').status, BulkStatus.existing);
    final v = one('brewed');
    expect(v.status, BulkStatus.variant);
    expect(v.word, 'brew');
    expect(v.copyWith(keepTyped: true).target, 'brewed');
    expect(one('zzqx').status, BulkStatus.unknown);
    final t = one('balcany');
    expect(t.status, BulkStatus.typo);
    expect(t.suggestion, 'balcony');
    expect(pack().similarTo('blacony'), ['balcony']); // swapped letters
    expect(t.willAdd, isFalse);
    final p = one('pick up');
    expect(p.status, BulkStatus.ready);
    expect(p.isPhrase, isTrue);
  });

  test('the bundled pack never folds a saved word; a downloaded one does', () {
    // Mac M365: the bundled pack said boring → bore and deleted boring at
    // every start, seconds before the downloaded pack said it was a word.
    final r = WordDatabaseRepository(clock: () => testNow)
      ..addWord(word: 'brewed', pos: 'verb', meaning: '');
    r.linkLexicon(pack()..bundled = true);
    expect(r.entryByWord('brewed'), isNotNull);
    r.linkLexicon(pack());
    expect(r.entryByWord('brewed'), isNull);
    expect(r.entryByWord('brew'), isNotNull);
  });

  test('the bundled pack does not move a saved word to another pos', () {
    // Mac M374: bundled pack had boring only as a verb form, moved the saved
    // adj. to verb, then the downloaded pack folded boring (verb) into bore.
    final r = WordDatabaseRepository(clock: () => testNow)
      ..addWord(word: 'balcony', pos: 'verb', meaning: '');
    r.linkLexicon(pack()..bundled = true);
    expect(r.entryByWord('balcony')!.pos, 'verb');
    r.linkLexicon(pack());
    expect(r.entryByWord('balcony')!.pos, 'noun');
  });

  test('a variant of a word already in the book is skipped', () {
    final r = repo()..addWord(word: 'brew', pos: 'verb', meaning: '釀造');
    expect(classifyBulkWord('brewed', r, pack()).status, BulkStatus.existing);
  });

  test('two forms of one word count once; the limit stops at 3000', () {
    final r = checkBulkWords('brewed, brewing', repo(), pack());
    expect(r.items.map((i) => i.status),
        [BulkStatus.variant, BulkStatus.merged]);
    expect(bulkAddLimit, 3000);
    // Mac M350: a base word and its form count once, in either order.
    for (final text in ['brew, brewed', 'brewed, brew']) {
      final items = checkBulkWords(text, repo(), pack()).items;
      expect(items.where((i) => i.willAdd).length, 1, reason: text);
      // The folded form is marked at check time (not left as "existing").
      expect(items.where((i) => i.status == BulkStatus.merged).length, 1,
          reason: text);
      final rr = repo();
      expect(addBulkItems(rr, items), (added: 1, skipped: 1));
    }
    final many = [for (var i = 0; i < 3005; i++) 'w$i'].join('\n');
    final big = checkBulkWords(many, repo(), pack());
    expect(big.items.length, bulkAddLimit);
    expect(big.overLimit, 5);
  });

  test('3000 words: only the first 300 unknown words get a suggestion, all add',
      () {
    final words = [
      for (var i = 0; i < bulkTypoCheckLimit; i++) 'q$i',
      'balcany',
      for (var i = 0; i < 2699; i++) 'x$i',
    ];
    final r = repo();
    final sw = Stopwatch()..start();
    final items = checkBulkWords(words.join('\n'), r, pack()).items;
    final balcany = items.firstWhere((i) => i.typed == 'balcany');
    expect(balcany.status, BulkStatus.unknown); // past the suggestion limit
    expect(addBulkItems(r, items).added, 3000);
    expect(sw.elapsed, lessThan(const Duration(seconds: 10)));
  });

  testWidgets('3000 rows in the preview do not overflow', (t) async {
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () => showBulkAddDialog(c, repo(), pack: pack()),
                child: const Text('go')))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const ValueKey('bulk-text')),
        [for (var i = 0; i < 3000; i++) 'w$i'].join('\n'));
    await t.tap(find.byKey(const ValueKey('bulk-check')));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.text('加入 3000 個'), findsOneWidget);
  });

  test('adding: skips existing and unconfirmed typos, adds the rest', () {
    final r = repo();
    final items =
        checkBulkWords('dog, brewed, balcany, zzqx, pick up', r, pack()).items;
    final res = addBulkItems(r, items);
    expect(res.added, 3);
    expect(res.skipped, 2);
    expect(r.entryByWord('brew'), isNotNull);
    expect(r.entryByWord('zzqx'), isNotNull);
    expect(r.entryByWord('pick up')?.pos, 'phrase');
    expect(r.entryByWord('balcany'), isNull);
  });

  testWidgets('check, take a suggestion, confirm', (t) async {
    final r = repo();
    ({int added, int skipped})? got;
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () async =>
                    got = await showBulkAddDialog(c, r, pack: pack()),
                child: const Text('go')))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    await t.enterText(
        find.byKey(const ValueKey('bulk-text')), 'dog\nbrewed\nbalcany');
    await t.tap(find.byKey(const ValueKey('bulk-check')));
    await t.pumpAndSettle();
    expect(find.text('dog'), findsOneWidget);
    expect(find.text('brewed → brew'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('bulk-suggest-2')));
    await t.pumpAndSettle();
    expect(find.text('加入 2 個'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('bulk-confirm')));
    await t.pumpAndSettle();
    expect(got, (added: 2, skipped: 1));
    expect(r.entryByWord('balcony'), isNotNull);
  });

  testWidgets('input does not overflow on a short phone with keyboard',
      (t) async {
    t.view.physicalSize = const Size(402, 420);
    t.view.devicePixelRatio = 1;
    t.view.viewInsets = const FakeViewPadding(bottom: 260);
    addTearDown(t.view.reset);
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () => showBulkAddDialog(c, repo(), pack: pack()),
                child: const Text('go')))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
  });
}
