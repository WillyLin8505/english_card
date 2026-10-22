import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/accent_audio.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// Card #227 round 147: the detail page always showed the pack's first IPA
// (British for 4,610 words that also have an American one), so 設定 美式
// showed /ˈkʌvə/ next to the American recording.
Map<String, dynamic> cover() => {
      'id': 1,
      'lemma': 'cover',
      'normalized': 'cover',
      'pos': 'verb',
      'status': 'full',
      'cefr': 'A2',
      'senses': [
        {'id': 1, 'definition': 'd', 'native': '覆蓋', 'labels': []},
      ],
      'pronunciations': [
        {'kind': 'ipa', 'value': '/ˈkʌvə/', 'accent': 'UK', 'default': true},
        {'kind': 'ipa', 'value': '/ˈkʌvɚ/', 'accent': 'US'},
      ],
    };

// Same round: 653 related words of slang/obsolete senses showed although
// those senses wait behind 顯示更多 (#528).
Map<String, dynamic> bust() => {
      'id': 2,
      'lemma': 'bust',
      'normalized': 'bust',
      'pos': 'noun',
      'status': 'full',
      'cefr': 'B2',
      'senses': [
        {'id': 20, 'definition': 'd', 'native': '半身像', 'labels': []},
        {'id': 21, 'definition': 'd', 'native': '突襲搜查', 'labels': ['slang']},
      ],
      'relations': [
        {'relation': 'synonyms', 'word': 'statue', 'native': '雕像', 'sense_id': 20},
        {'relation': 'synonyms', 'word': 'raid', 'native': '突襲', 'sense_id': 21},
      ],
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => LexiconPack.instance.loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'created_at': '1',
        'lexemes': [cover(), bust()],
      }));
  tearDown(() => LexiconPack.instance.clear());

  Future<void> open(WidgetTester tester, String accent,
      {String word = 'cover', String pos = 'verb'}) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: word, pos: pos, meaning: '').id;
    repo.linkLexicon(LexiconPack.instance);
    await pumpApp(tester,
        repository: repo,
        settings: AppSettings.inMemory(englishAccent: accent),
        home: WordDetailScreen(wordEntryId: id));
  }

  testWidgets('美式 shows the American IPA', (tester) async {
    await open(tester, 'en-US');
    expect(find.text('/ˈkʌvɚ/'), findsOneWidget);
    expect(find.text('/ˈkʌvə/'), findsNothing);
  });

  testWidgets('英式 shows the British IPA', (tester) async {
    await open(tester, 'en-GB');
    expect(find.text('/ˈkʌvə/'), findsOneWidget);
  });

  testWidgets('a slang sense brings no related words', (tester) async {
    await open(tester, 'en-GB', word: 'bust', pos: 'noun');
    expect(find.textContaining('statue'), findsOneWidget);
    expect(find.textContaining('raid'), findsNothing);
  });

  test('an IPA the learner typed is kept', () {
    final source = LexiconPack.instance.lookup('cover', pos: 'verb')!.entry;
    expect(packAccentIpa(source, 'en-US'), '/ˈkʌvɚ/');
    final typed = WordEntry(
        id: 'w',
        word: 'cover',
        pos: 'verb',
        meaning: '覆蓋',
        ipa: '/kʌvər/',
        ipaSource: 'user',
        createdAt: testNow,
        updatedAt: testNow);
    expect(accentIpa(typed, 'en-US'), '/kʌvər/');
  });
}
