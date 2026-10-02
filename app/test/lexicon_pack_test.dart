import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _pack() => {
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': '2026-09-25T07:15:00Z',
      'labels': {'pos:noun': '名詞'},
      'redirects': {'99': 1},
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'zipf': 4.8,
          'senses': [
            {
              'id': 10,
              'definition': 'A round fruit.',
              'native': '蘋果',
              'native_ai': false
            },
          ],
          'forms': [
            {
              'field': 'noun_plural',
              'form': 'apples',
              'normalized': 'apples',
              'label': '名詞複數'
            },
          ],
          'pronunciations': [
            {'kind': 'ipa', 'value': '/ˈæp.əl/', 'accent': 'US'},
            {'kind': 'audio', 'audio': 'audio/en/abc.mp3', 'default': true},
          ],
          'examples': [
            {
              'text': 'I ate an apple.',
              'translation': '我吃了一顆蘋果。',
              'translation_ai': false,
              'level': 'A2'
            },
          ],
          'relations': [
            {
              'relation': 'synonyms',
              'word': 'pome',
              'lexeme_id': 50,
              'native': '梨果',
              'cefr': 'C2',
              'zipf': 2.1,
              'rarity': 'very_rare',
              'hide_by_default': true
            },
          ],
          'morphemes': [
            {'part': 'apple', 'kind': 'root', 'meaning': null, 'native': '蘋果'},
          ],
        },
        {
          'id': 2,
          'lemma': 'exterior',
          'normalized': 'exterior',
          'pos': 'adj',
          'status': 'full',
          'senses': [
            {'id': 20, 'definition': 'Outer.', 'native': null},
          ],
          'morphemes': [
            {'part': 'ex', 'kind': 'root', 'meaning': 'out', 'native': '向外、出'},
            {
              'part': '-ter',
              'kind': 'suffix',
              'meaning': 'side',
              'native': '…側'
            },
            {
              'part': '-ior',
              'kind': 'suffix',
              'meaning': 'more',
              'native': '較…的'
            },
          ],
        },
        {
          'id': 50,
          'lemma': 'pome',
          'normalized': 'pome',
          'pos': 'noun',
          'status': 'stub'
        },
      ],
    };

WordCandidate _cand(String word, {String pos = 'noun', String meaning = ''}) =>
    WordCandidate(
      word: word,
      pos: pos,
      meaning: meaning,
      level: 'A1',
      levelSource: 'cefr-j',
      point: const LabelPoint(0.5, 0.5),
    );

void main() {
  late LexiconPack pack;
  setUp(() => pack = LexiconPack()..loadJson(_pack()));

  test('looks up lemma + part of speech, then lemma, then inflected forms', () {
    expect(pack.lookup('Apple', pos: 'noun')!.via, 'lemma+pos');
    expect(pack.lookup('apple', pos: 'verb')!.via, 'lemma');
    final viaForm = pack.lookup('apples');
    expect(viaForm!.entry.lemma, 'apple');
    expect(viaForm.via, 'form');
    expect(pack.lookup('exterior', pos: 'adj.')!.entry.id, 2);
    expect(pack.lookup('pome'), isNull,
        reason: 'stubs are link targets, not entries');
    expect(pack.byId(99)!.lemma, 'apple', reason: 'merged ids redirect');
    expect(pack.size, 2);
  });

  test(
      'linking gives recognized words their lexeme id, lemma and native meaning',
      () {
    final linked = pack.linkAll(
        [_cand('apples'), _cand('bread'), _cand('exterior', pos: 'adj.')]);
    expect(linked[0].word, 'apple');
    expect(linked[0].lexemeId, 1);
    expect(linked[0].meaning, '蘋果');
    expect(linked[1].inDatabase, isFalse);
    expect(linked[2].lexemeId, 2);
    // Missing word and missing native meaning are recorded for the admin.
    expect(pack.requests.values.map((r) => '${r.kind}:${r.lemma}'),
        containsAll(['missing_lexeme:bread', 'missing_localization:exterior']));
  });

  test('the pack entry becomes the word detail of a new word', () {
    final d = pack.detail('apple')!;
    expect(d.ipa, '/ˈæp.əl/');
    expect(d.wordAudioUrl, 'assets/lexicon/media/audio/en/abc.mp3');
    expect(d.exampleSentences.single.zh, '我吃了一顆蘋果。');
    expect(d.exampleSentences.single.difficulty, 'A2');
    expect(d.synonyms, ['pome']);
    expect(d.relations.single.hideByDefault, isTrue);
    expect(d.inflections.single.form, 'apples');
    expect(pack.lookup('exterior')!.entry.breakdown, 'ex + -ter + -ior');
  });

  test('linkLexicon links saved photos and words already in the database', () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final photo = Photo(
      id: 'p1',
      title: 'fruit',
      takenAt: testNow,
      createdAt: testNow,
      candidates: [_cand('apples')],
    );
    repo.addPhoto(photo);
    final e = repo.addWord(word: 'apple', pos: 'noun', meaning: '');
    expect(repo.linkLexicon(pack), 2);
    expect(repo.photo('p1')!.candidates.single.lexemeId, 1);
    final linked = repo.entry(e.id)!;
    expect(linked.lexemeId, 1);
    expect(linked.meaning, '蘋果');
    expect(linked.examples.first.translation, '我吃了一顆蘋果。');
    expect(linked.examples.first.difficulty, 'A2');
    expect(linked.related.single.hideByDefault, isTrue);
    expect(linked.relatedOf({RelationType.synonym}), isEmpty,
        reason:
            'very rare relation words stay in the database but are hidden in learning UI');
    expect(repo.linkLexicon(pack), 0,
        reason: 'nothing changes the second time');
  });

  test('a newer pack updates the translation of a sentence the word already has', () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final e = repo.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');
    const old = WordExample(text: 'I ate an apple.', translation: '我吃了一個苹果。');
    repo.editEntry(repo.entry(e.id)!.copyWith(examples: [old]), {});
    repo.linkLexicon(pack);
    final synced = repo.entry(e.id)!.examples;
    expect(synced.first.translation, '我吃了一顆蘋果。');
    expect(synced.where((x) => x.text == 'I ate an apple.'), hasLength(1));
    // A sentence the learner edited stays theirs.
    final mine = repo.addWord(word: 'apples', pos: 'noun', meaning: '');
    repo.editEntry(
        repo.entry(mine.id)!.copyWith(examples: [
          const WordExample(text: 'I ate an apple.', translation: '我的翻譯')
        ]),
        {WordField.examples});
    repo.linkLexicon(pack);
    expect(repo.entry(mine.id)!.examples.single.translation, '我的翻譯');
  });
}
