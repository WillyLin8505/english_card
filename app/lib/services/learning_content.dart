import '../models/word_entry.dart';
import 'lexicon_pack.dart';

/// Stable dictionary codes; unknown non-word types remain visibly classified.
String entryTypeLabel(String value) {
  if (value == 'word') return '';
  final labels = LexiconPack.instance.labels;
  return labels['entry_type:$value'] ?? labels['entry_type.$value'] ?? labels[value] ?? switch (value) {
    'phrasal_verb' => '片語動詞',
    'idiom' => '慣用語',
    'collocation' => '搭配詞',
    'fixed_expression' => '固定表達',
    _ => '片語',
  };
}

String typedMeaning(String meaning, String entryType) {
  final label = entryTypeLabel(entryType);
  return label.isEmpty ? meaning : '[$label]${meaning.isEmpty ? '' : ' $meaning'}';
}

String posLabel(String value) => switch (value) {
      'noun' || 'n.' => '名詞',
      'verb' || 'v.' => '動詞',
      // The lexicon pack uses Wiktionary's short codes (adj, adv, intj…).
      'adj.' || 'adj' || 'adjective' => '形容詞',
      'adv.' || 'adv' || 'adverb' => '副詞',
      'pronoun' || 'pron' => '代名詞',
      'preposition' || 'prep' => '介系詞',
      'conjunction' || 'conj' => '連接詞',
      'interjection' || 'intj' => '感嘆詞',
      'determiner' || 'det' || 'article' => '限定詞',
      'numeral' || 'num' => '數詞',
      'phrase' => '片語',
      'proper noun' || 'proper_noun' => '專有名詞',
      _ => '其他詞性',
    };

String levelLabel(String value) => '${switch (value) {
      'A1' => '入門',
      'A2' => '基礎',
      'B1' => '中階',
      'B2' => '中高階',
      'C1' => '進階',
      'C2' => '精通',
      _ => '未分級',
    }}（$value）';

String formLabel(String value) => switch (value) {
      'plural' || 'noun_plural' => '複數',
      'past' || 'past tense' || 'verb_past' => '過去式',
      'present participle' || 'gerund' || 'verb_present_participle' => '現在分詞',
      'past participle' || 'verb_past_participle' => '過去分詞',
      'third-person singular' || 'verb_third_person' => '第三人稱單數',
      'comparative' || 'adjective_comparative' => '比較級',
      'superlative' || 'adjective_superlative' => '最高級',
      _ => RegExp(r'[\u4e00-\u9fff]').hasMatch(value) ? value : '變化形',
    };

// Keep in sync with lexicon/backend/app/quality.py example_is_charged.
final _chargedSex = RegExp(
    r"\b(?:sex(?:es|ual\w*|y)?|nude|naked|porn|orgasm|prostitute|whore|slut|rape|rapist|penis|vagina|erotic|intercourse|adultery|adulter\w*|fornicat\w*|brothel|masturbat\w*|condom|genital)\b",
    caseSensitive: false);
final _chargedViolence = RegExp(
    r"\b(?:murder(?:ed|ing|s|er|ers|ous)?|kill(?:ed|ing|s|er|ers)?|shoot(?:ing|s|er|ers)?|bullet|guns?|stab(?:bed|bing|s)?|bombs?|suicide|torture)\b",
    caseSensitive: false);
final _chargedReligion = RegExp(
    r"\b(?:god|jesus|christ|allah|bible|quran|koran|mosque|church|priest|buddha|buddhist|worship|prayer|scripture|gospel|heaven|hell)\b",
    caseSensitive: false);
final _chargedPolitics = RegExp(
    r"\b(?:migration|immigrant|immigration|refugee|asylum|abortion|bolshevik|communist|communism|nazi|hitler|genocide|trump|biden|feminis\w*|parliament|dictator\w*|propaganda)\b",
    caseSensitive: false);
final _chargedStanceNoun = RegExp(
    r"\b(?:woman|women|migration|immigrants?|abortion|gender|pronouns?)\b",
    caseSensitive: false);
final _chargedBan = RegExp(
    r"\b(?:outlaw(?:ed|ing|s)?|ban(?:ned|ning)?)\b",
    caseSensitive: false);
final _chargedSoft = RegExp(
    r"\b(?:oh my god|thank god|for god'?s sake|god knows|what the hell|the hell)\b",
    caseSensitive: false);
const _stanceLemmas = {
  'woman',
  'women',
  'migration',
  'immigrant',
  'abortion',
  'gender',
  'pronoun',
};

bool _chargedForeign(RegExp pattern, String source, String lemma) {
  final low = lemma.toLowerCase();
  for (final match in pattern.allMatches(source)) {
    final hit = match.group(0)!.toLowerCase();
    if (low.isNotEmpty && (hit.startsWith(low) || low.startsWith(hit))) continue;
    return true;
  }
  return false;
}

/// Politics, religion, violence or sex that is not the headword itself.
/// Same categories as the lexicon ranker. Null when the sentence is ordinary
/// or the topic word is the one being taught (church may mention a church).
String? exampleIsCharged(String text, String lemma) {
  if (_chargedForeign(_chargedSex, text, lemma)) return 'sex';
  if (_chargedForeign(_chargedViolence, text, lemma)) return 'violence';
  if (_chargedForeign(_chargedPolitics, text, lemma)) return 'politics';
  if (_chargedForeign(_chargedReligion, text.replaceAll(_chargedSoft, ' '), lemma)) {
    return 'religion';
  }
  if (!_stanceLemmas.contains(lemma.toLowerCase()) &&
      _chargedStanceNoun.hasMatch(text) &&
      _chargedBan.hasMatch(text)) {
    return 'politics';
  }
  return null;
}

/// Only translated examples appear in learning views. Spec section 7: the
/// learner's own CEFR level first, then the adjacent levels (the easier one
/// before the harder one), shorter sentences first within a level; nothing
/// more than one level above the learner. A neutral sentence is preferred
/// over a political, religious, violent or sexual one (問題回報 #254).
/// Source data remains intact.
List<WordExample> learningExamples(WordEntry entry, String level, {int maxItems = 5}) {
  final seen = <String>{};
  final at = levelIndex(level);
  final examples = entry.examples
      .where((e) =>
          (e.translation ?? '').trim().isNotEmpty &&
          !isColumnWordList(e.text, entry.word) &&
          seen.add(e.text.toLowerCase()) &&
          (e.difficulty == null || levelIndex(e.difficulty) <= at + 1))
      .toList();
  // Unleveled sentences rank with the learner's level.
  int distance(WordExample e) {
    final d = e.difficulty == null ? 0 : levelIndex(e.difficulty) - at;
    return d == 0 ? 0 : (d < 0 ? -2 * d - 1 : 2 * d);
  }

  int words(WordExample e) => e.text.split(' ').length;
  int charged(WordExample e) => exampleIsCharged(e.text, entry.word) == null ? 0 : 1;
  examples.sort((a, b) {
    final topic = charged(a).compareTo(charged(b));
    if (topic != 0) return topic;
    final c = distance(a).compareTo(distance(b));
    return c != 0 ? c : words(a).compareTo(words(b));
  });
  return examples.take(maxItems).toList();
}

/// Short lowercase compound names laid out in columns are glossary lists.
/// This is deliberately not a general grammatical sentence classifier.
bool isColumnWordList(String text, String lemma) {
  final parts = text
      .split(RegExp(r'\t+|[\u2002-\u200a]{2,}| {3,}'))
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList();
  final head = lemma.trim().toLowerCase();
  return head.isNotEmpty &&
      parts.length >= 2 &&
      parts.every((p) =>
          p == p.toLowerCase() &&
          RegExp(r"^[a-z'’ -]+$").hasMatch(p) &&
          p.split(RegExp(r'\s+')).length <= 4 &&
          (p == head || p.endsWith(' $head')));
}

/// Do not turn noisy legacy association/spelling lists into teaching claims.
/// Show only explicitly typed, translated and common dictionary relations.
List<({String word, String meaning})> learningRelations(
    WordEntry entry, String level, String kind, {int maxItems = 5}) {
  if (entry.userEdited.contains(WordField.related)) {
    return [
      for (final r in entry.related)
        if (r.type == relationTypeFromKey(kind) && !r.hideByDefault)
          (word: r.word, meaning: r.native ?? '')
    ].take(maxItems).toList();
  }
  final pack = LexiconPack.instance;
  final source = pack.lookup(entry.word, pos: entry.pos)?.entry;
  if (source == null || source.pos != LexiconPack.packPos(entry.pos)) return [];
  final seen = <String>{};
  return [
    for (final r in source.relations)
      if (r.relation == kind &&
          !r.hideByDefault &&
          (r.native ?? '').trim().isNotEmpty &&
          r.cefr != null &&
          levelIndex(r.cefr) <= levelIndex(level) &&
          // Level, not frequency: the admin keeps three a level up to C2
          // (spec 08), and C1/C2 words are 「rare」 by frequency. Very rare
          // ones come marked hideByDefault (問題回報 #96).
          r.word.toLowerCase() != entry.word.toLowerCase() &&
          seen.add(r.word.toLowerCase()))
        (word: r.word, meaning: r.native!)
  ].take(maxItems).toList();
}

/// The word's origin for the card back and word page, in the learner's
/// language only (spec 08: 可閱讀的母語解釋；不可只有未翻譯的來源語文字).
/// Until the admin has it, the word list names 詞源 as missing.
String? learningEtymology(WordEntry entry) {
  if (entry.userEdited.contains(WordField.etymology)) return entry.etymology;
  final source = LexiconPack.instance.lookup(entry.word, pos: entry.pos)?.entry;
  return source?.etymology?.native;
}

/// 構詞 with each part's meaning in the learner's language — con-（共同）＋
/// serve（服務）＋ -ation（行為） — or nothing when the word is one part
/// (spec 08: 字根…可閱讀的母語解釋). Without the pack: the stored parts.
String? learningMorphology(WordEntry entry) {
  if (entry.userEdited.contains(WordField.morphology)) return entry.morphology;
  final source = LexiconPack.instance.lookup(entry.word, pos: entry.pos)?.entry;
  final parts = source?.morphemes ?? const <LexMorpheme>[];
  if (parts.length > 1) {
    return parts
        .map((m) => (m.native ?? '').trim().isEmpty
            ? m.part
            : '${m.part}（${m.native!.split(RegExp('[、；]')).first}）')
        .join(' ＋ ');
  }
  if (source != null) return null;
  final stored = [if (entry.root != null) entry.root!, ...entry.affixes];
  return stored.length > 1 ? stored.join(' ＋ ') : null;
}

/// Same conservative native-gloss ambiguity rule as the card preview. A shared
/// meaning would make a word-to-meaning matching question have multiple answers.
bool nativeGlossesOverlap(String a, String b) {
  Iterable<String> keys(String text) => text
      .split(RegExp(r'[、，,;；/／|｜]+'))
      .map((part) => part
          .replaceAll(RegExp(r'[（(][^）)]*[）)]'), '')
          .replaceAll(RegExp(r'\s+'), ' ')
          .trim()
          .toLowerCase())
      .where((part) => part.isNotEmpty);
  for (final x in keys(a)) {
    for (final y in keys(b)) {
      final short = x.length <= y.length ? x : y;
      final long = x.length <= y.length ? y : x;
      if (short == long || (short.length >= 2 && long.contains(short))) {
        return true;
      }
    }
  }
  return false;
}
