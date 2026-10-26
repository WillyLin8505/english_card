import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
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
              'register': 'spoken',
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

  test('a lookup without a part of speech gets the main one (card #393)', () {
    Map<String, dynamic> lex(int id, String pos, int rank) => {
          'id': id,
          'lemma': 'sunshine',
          'normalized': 'sunshine',
          'pos': pos,
          'status': 'full',
          'usage_rank': rank,
          'rare_usage': rank > 0,
          'senses': [
            {'id': id * 10, 'definition': 'd', 'native': pos}
          ],
        };
    final p = LexiconPack()
      ..loadJson({
        'schema_version': 3,
        'target_language': 'en',
        'native_language': 'zh-TW',
        'created_at': '2026-09-25T07:15:00Z',
        'lexemes': [lex(2, 'adj', 1), lex(1, 'noun', 0)],
      });
    expect(p.lookup('sunshine')!.entry.pos, 'noun');
    expect(p.lookup('sunshine', pos: 'adj')!.entry.pos, 'adj');
  });

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

  test('a form used as another part of speech finds its own word (#51)', () {
    Map<String, dynamic> entry(int id, String lemma, String pos,
            {List<String> forms = const []}) =>
        {
          'id': id,
          'lemma': lemma,
          'normalized': lemma,
          'pos': pos,
          'status': 'full',
          'senses': const [],
          'forms': [
            for (final f in forms)
              {'field': 'verb_present_participle', 'form': f, 'normalized': f}
          ],
        };
    final p = LexiconPack()
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          entry(1, 'lie', 'verb', forms: ['lying']),
          entry(2, 'lying', 'adj'),
        ],
      });
    // A dog lying on the grass: lie, not lying 說謊的.
    final verb = p.lookup('lying', pos: 'verb')!;
    expect((verb.entry.lemma, verb.via), ('lie', 'form'));
    expect(p.lookup('lying', pos: 'adj.')!.entry.id, 2);
    expect(p.lookup('lying')!.entry.id, 2,
        reason: 'no part of speech: the word itself');
  });

  test('a form that shares its word\'s card is that word on the card (#51)',
      () {
    final p = LexiconPack()
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {
            'id': 1,
            'lemma': 'tether',
            'normalized': 'tether',
            'pos': 'verb',
            'status': 'full',
            'senses': [
              {'id': 10, 'definition': 'To tie with a tether.', 'native': '拴住'}
            ],
            'forms': [
              {
                'field': 'verb_third_person',
                'form': 'tethers',
                'normalized': 'tethers'
              },
              {
                'field': 'verb_past_participle',
                'form': 'tethered',
                'normalized': 'tethered'
              },
            ],
          },
          {
            'id': 2,
            'lemma': 'tethered',
            'normalized': 'tethered',
            'pos': 'adj',
            'status': 'full',
            'card': 'tether',
            'senses': [
              {'id': 20, 'definition': 'Tied.', 'native': '被拴住的'}
            ],
          },
          {
            'id': 4,
            'lemma': 'tethered',
            'normalized': 'tethered',
            'pos': 'verb',
            'status': 'full',
            'card': 'tether',
            'card_form': true,
            'senses': [
              {
                'id': 40,
                'definition': 'Past of tether.',
                'native': 'tether 的過去式'
              }
            ],
          },
          {
            'id': 3,
            'lemma': 'left',
            'normalized': 'left',
            'pos': 'adj',
            'status': 'full',
            'senses': [
              {'id': 30, 'definition': 'On the west side.', 'native': '左邊的'}
            ],
          },
        ],
      });
    final hit = p.lookup('tethered', pos: 'adj.')!;
    expect((hit.entry.lemma, hit.via), ('tether', 'family'));
    expect(p.link(_cand('tethered', pos: 'adj.')).word, 'tether');
    expect(p.lookup('left', pos: 'adj.')!.entry.id, 3,
        reason: 'a word spelt like a form but meaning something else');
    // tether's card shows what tethered means, first.
    final forms = p.detailFor(hit.entry).inflections;
    expect(
        (forms.first.form, forms.first.label), ('tethered', '過去分詞・形容詞：被拴住的'));
    expect((forms[1].form, forms[1].label), ('tethers', 'verb_third_person'));
  });

  test('a word saved under a form joins its word\'s card (#51)', () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addPhoto(Photo(
        id: 'p1',
        title: 'fruit',
        takenAt: testNow,
        createdAt: testNow,
        candidates: [_cand('apples')]));
    // Saved under the form before it shared apple's card, and reviewed once.
    repo.savePhotoWords(
        'p1', [ListedWord(_cand('apples'), const LabelPoint(0.5, 0.5))],
        difficultyOffset: 0);
    final apples = repo.entryByWord('apples')!;
    final reviewed = repo.cardOf(apples.id)!;
    repo.review(reviewed.id, Rating.good);
    final apple = repo.addWord(word: 'apple', pos: 'noun', meaning: '');

    repo.linkLexicon(pack);
    expect(repo.entryByWord('apples'), isNull);
    expect(repo.occurrencesInPhoto('p1').single.wordEntryId, apple.id);
    expect(repo.cardOf(apple.id)!.id, reviewed.id,
        reason: 'the reviewed card stays, with its history');
    expect(repo.logsOf(reviewed.id), hasLength(1));
    expect(repo.cardCount, 1);
    expect(repo.profile.familiarityOf('apple'), Familiarity.learning);
    expect(repo.profile.familiarityOf('apples'), Familiarity.unknown);
    expect(repo.linkLexicon(pack), 0, reason: 'folded once');
  });

  test('a form saved without its word becomes the word, card and all (#51)',
      () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final apples = repo.addWord(word: 'apples', pos: 'noun', meaning: '');
    final card = repo.cardOf(apples.id)!;
    repo.linkLexicon(pack);
    final now = repo.entry(apples.id)!;
    expect((now.word, now.lexemeId, now.meaning), ('apple', 1, '蘋果'));
    expect(repo.cardOf(apples.id)!.id, card.id);
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
    expect(d.definitions.single.register, 'spoken');
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
    expect(linked.register, 'spoken');
    expect(linked.examples.first.translation, '我吃了一顆蘋果。');
    expect(linked.examples.first.difficulty, 'A2');
    expect(linked.related.single.hideByDefault, isTrue);
    expect(linked.relatedOf({RelationType.synonym}), isEmpty,
        reason:
            'very rare relation words stay in the database but are hidden in learning UI');
    expect(repo.linkLexicon(pack), 0,
        reason: 'nothing changes the second time');
  });

  test(
      'a newer pack updates the translation of a sentence the word already has',
      () {
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
    // apples shares apple's card (#51); the learner's sentence comes along
    // and stays theirs.
    expect(repo.entry(mine.id), isNull);
    final apple = repo.entry(e.id)!;
    expect(apple.examples.single.translation, '我的翻譯');
    expect(apple.userEdited, contains(WordField.examples));
  });

  // 問題回報 #706: city lights at night were labelled Illuminate
  // 「（宗教）受啟蒙的…」 — the rare adjective, picked for its part of speech.
  test('a form goes to its word\'s common entry, not a rare one',
      () {
    final p = LexiconPack()
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {
            'id': 1,
            'lemma': 'illuminate',
            'normalized': 'illuminate',
            'pos': 'verb',
            'status': 'full',
            'cefr': 'B1',
            'senses': [
              {'id': 10, 'definition': 'To shine light on.', 'native': '照亮、照明'}
            ],
          },
          {
            'id': 2,
            'lemma': 'illuminate',
            'normalized': 'illuminate',
            'pos': 'adj',
            'status': 'full',
            'cefr': 'C2',
            'rare_usage': true,
            'usage_rank': 1,
            'senses': [
              {'id': 20, 'definition': 'Enlightened spiritually.', 'native': '（宗教）受啟蒙的'}
            ],
          },
          {
            'id': 3,
            'lemma': 'illuminated',
            'normalized': 'illuminated',
            'pos': 'adj',
            'status': 'full',
            'card': 'illuminate',
            'senses': [
              {'id': 30, 'definition': 'Lit.', 'native': '被光照射，發光'}
            ],
          },
        ],
      });
    expect(p.lookup('illuminated', pos: 'adj.')!.entry.id, 1);
    expect(p.link(_cand('illuminated', pos: 'adj.')).meaning, '照亮、照明');
  });
}
