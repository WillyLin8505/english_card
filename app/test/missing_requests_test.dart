import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  test('words the pack lacks are sent once to /api/missing (spec: 缺詞條)', () async {
    LexiconPack.instance
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {'id': 1, 'lemma': 'apple', 'normalized': 'apple', 'pos': 'noun', 'status': 'full',
           'senses': [{'id': 10, 'definition': 'A fruit.', 'native': null}]},
        ],
      })
      ..requests.clear();
    WordCandidate c(String w) => WordCandidate.fromJson({'word': w, 'pos': 'noun', 'level': 'A1', 'point': {'x': 0.5, 'y': 0.5}});
    LexiconPack.instance.link(c('texture'));
    LexiconPack.instance.link(c('apple'));
    final bodies = <Map<String, dynamic>>[];
    var fail = true;
    final s = DictionarySync(client: MockClient((r) async {
      expect(r.url.path, '/api/missing');
      if (fail) return http.Response('down', 503);
      bodies.add(jsonDecode(r.body) as Map<String, dynamic>);
      return http.Response('{"saved":2}', 200);
    }));
    expect(await s.sendMissing(), 0, reason: 'a failure keeps them for the next try');
    fail = false;
    expect(await s.sendMissing(), 2);
    final sent = {for (final x in bodies.single['requests'] as List) (x as Map)['kind']: x};
    expect(sent['missing_lexeme']!['lemma'], 'texture');
    expect(sent['missing_lexeme']!['target'], 'en');
    expect(sent['missing_localization']!['lexeme_id'], 1);
    expect(await s.sendMissing(), 0, reason: 'nothing new');
    LexiconPack.instance.link(c('pebble'));
    expect(await s.sendMissing(), 1);
  });
}
