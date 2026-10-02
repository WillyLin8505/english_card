import '../models/word_entry.dart';
import 'lexicon_pack.dart';

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

/// Only translated examples appear in learning views. Spec section 7: the
/// learner's own CEFR level first, then the adjacent levels (the easier one
/// before the harder one), shorter sentences first within a level; nothing
/// more than one level above the learner. Source data remains intact.
List<WordExample> learningExamples(WordEntry entry, String level) {
  final seen = <String>{};
  final at = levelIndex(level);
  final examples = entry.examples
      .where((e) =>
          (e.translation ?? '').trim().isNotEmpty &&
          seen.add(e.text.toLowerCase()) &&
          (e.difficulty == null || levelIndex(e.difficulty) <= at + 1))
      .toList();
  // Unleveled sentences rank with the learner's level.
  int distance(WordExample e) {
    final d = e.difficulty == null ? 0 : levelIndex(e.difficulty) - at;
    return d == 0 ? 0 : (d < 0 ? -2 * d - 1 : 2 * d);
  }

  int words(WordExample e) => e.text.split(' ').length;
  examples.sort((a, b) {
    final c = distance(a).compareTo(distance(b));
    return c != 0 ? c : words(a).compareTo(words(b));
  });
  return examples.take(5).toList();
}

/// Do not turn noisy legacy association/spelling lists into teaching claims.
/// Show only explicitly typed, translated and common dictionary relations.
List<({String word, String meaning})> learningRelations(
    WordEntry entry, String level, String kind) {
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
  ].take(5).toList();
}

/// The word's origin for the card back and word page, in the learner's
/// language only (spec 08: 可閱讀的母語解釋；不可只有未翻譯的來源語文字).
/// Until the admin has it, the word list names 詞源 as missing.
String? learningEtymology(WordEntry entry) {
  final source = LexiconPack.instance.lookup(entry.word, pos: entry.pos)?.entry;
  return source?.etymology?.native;
}

/// 構詞 with each part's meaning in the learner's language — con-（共同）＋
/// serve（服務）＋ -ation（行為） — or nothing when the word is one part
/// (spec 08: 字根…可閱讀的母語解釋). Without the pack: the stored parts.
String? learningMorphology(WordEntry entry) {
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

