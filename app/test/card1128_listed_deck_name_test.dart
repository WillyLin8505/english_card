// 問題回報 #1625 (#1025/#1548): the installed deck keeps the name the list
// showed for the user's native language; the detail endpoint answers in Chinese.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/deck_library.dart';

void main() {
  test('fetchDeck(listed:) keeps the listed (English) title', () async {
    final lib = DeckLibrary(
        client: MockClient((_) async => http.Response(
            jsonEncode({
              'slug': 'fr-basic-3000',
              'kind': 'words',
              'title': '法語基礎 3000 字',
              'items': [
                {'word': 'maison', 'pos': 'noun', 'cefr': 'A1'}
              ],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'})),
        remote: true,
        persist: false);
    const listed = DeckInfo(
        slug: 'fr-basic-3000',
        kind: 'words',
        title: 'French Basic 3000 Words',
        count: 1);
    final c = await lib.fetchDeck('fr-basic-3000', listed: listed);
    expect(c.info.title, 'French Basic 3000 Words');
    expect(c.words, hasLength(1));
  });
}
