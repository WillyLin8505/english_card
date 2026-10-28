import 'lexicon_pack.dart';
import 'word_database_repository.dart';

/// 一次加入多個單字 (card #745): split pasted text into words, then say what
/// would happen to each one before anything is added.

/// Most words one paste may hold (owner 10/29: 3000).
const bulkAddLimit = 3000;

/// Unknown words that get a spelling suggestion; each one scans the whole
/// pack, so later unknown words are just "not in the dictionary".
const bulkTypoCheckLimit = 300;

enum BulkStatus {
  /// In the dictionary; will be added.
  ready,

  /// Already in the 單字本; skipped.
  existing,

  /// An inflected form (brewed); added as its base word (brew) unless the
  /// learner switches back.
  variant,

  /// Not in the dictionary; still added, data is filled in the background.
  unknown,

  /// Not in the dictionary but a close spelling is; add nothing until the
  /// learner takes the suggestion or keeps the typed word.
  typo,
}

class BulkItem {
  /// As typed (lower case).
  final String typed;
  final BulkStatus status;

  /// The word that will be added (the base word for a [BulkStatus.variant]).
  final String word;
  final String pos;
  final String? level;
  final String meaning;

  /// Closest dictionary word for a [BulkStatus.typo].
  final String? suggestion;

  /// For a [BulkStatus.variant]: the learner kept the typed form.
  final bool keepTyped;

  /// For [BulkStatus.unknown] / [BulkStatus.typo]: the learner adds it anyway.
  final bool include;

  const BulkItem({
    required this.typed,
    required this.status,
    required this.word,
    required this.pos,
    this.level,
    this.meaning = '',
    this.suggestion,
    this.keepTyped = false,
    this.include = true,
  });

  bool get isPhrase => pos == 'phrase';

  /// Whether confirming adds this word.
  bool get willAdd => status != BulkStatus.existing && include;

  /// The spelling that will be added.
  String get target => status == BulkStatus.variant && keepTyped ? typed : word;

  BulkItem copyWith({bool? include, bool? keepTyped}) => BulkItem(
      typed: typed,
      status: status,
      word: word,
      pos: pos,
      level: level,
      meaning: meaning,
      suggestion: suggestion,
      keepTyped: keepTyped ?? this.keepTyped,
      include: include ?? this.include);
}

class BulkParse {
  final List<BulkItem> items;

  /// Words past [bulkAddLimit], not looked at.
  final int overLimit;

  const BulkParse(this.items, this.overLimit);
}

/// Words in [text]: one per line, or split by comma, 、, ，, ；, semicolon or
/// Tab. Blanks and repeats (any case) are dropped.
List<String> splitBulkWords(String text) {
  final seen = <String>{};
  final out = <String>[];
  for (final raw in text.split(RegExp(r'[\n\r\t,，、;；]+'))) {
    final w = raw.trim().replaceAll(RegExp(r'\s+'), ' ').toLowerCase();
    if (w.isNotEmpty && seen.add(w)) out.add(w);
  }
  return out;
}

BulkParse checkBulkWords(
    String text, WordDatabaseRepository repo, LexiconPack pack) {
  final words = splitBulkWords(text);
  final over = words.length > bulkAddLimit ? words.length - bulkAddLimit : 0;
  var typoChecks = bulkTypoCheckLimit;
  final items = <BulkItem>[];
  for (final w in words.take(bulkAddLimit)) {
    final i = classifyBulkWord(w, repo, pack, suggest: typoChecks > 0);
    if (i.status == BulkStatus.unknown || i.status == BulkStatus.typo) {
      typoChecks--;
    }
    items.add(i);
  }
  // Two typed forms can lead to one base word (brewed, brewing → brew), and a
  // base word typed as is keeps it whatever order they came in (Mac M350:
  // abandon + abandoned counted twice, so 57 fewer were added than the button said).
  final taken = {
    for (final i in items)
      if (i.status == BulkStatus.ready) i.word
  };
  return BulkParse([
    for (final i in items)
      if (i.status == BulkStatus.variant && !taken.add(i.word))
        BulkItem(
            typed: i.typed,
            status: BulkStatus.existing,
            word: i.word,
            pos: i.pos)
      else
        i
  ], over);
}

BulkItem classifyBulkWord(
    String w, WordDatabaseRepository repo, LexiconPack pack,
    {bool suggest = true}) {
  final phrase = w.contains(' ');
  if (repo.entryByWord(w) != null) {
    return BulkItem(
        typed: w, status: BulkStatus.existing, word: w, pos: 'noun');
  }
  final hit = pack.isEmpty ? null : pack.lookup(w);
  if (hit == null) {
    final near =
        pack.isEmpty || phrase || !suggest ? const <String>[] : pack.similarTo(w);
    return BulkItem(
        typed: w,
        status: near.isEmpty ? BulkStatus.unknown : BulkStatus.typo,
        word: w,
        pos: phrase ? 'phrase' : 'noun',
        suggestion: near.firstOrNull,
        include: near.isEmpty);
  }
  final e = hit.entry;
  final base = e.normalized;
  final pos = _appPos(e.pos, phrase ? 'phrase' : 'noun');
  if (repo.entryByWord(base) != null) {
    return BulkItem(
        typed: w, status: BulkStatus.existing, word: base, pos: pos);
  }
  return BulkItem(
      typed: w,
      status: base != w ? BulkStatus.variant : BulkStatus.ready,
      word: base,
      pos: pos,
      level: e.cefr,
      meaning: e.learnerMeaning ?? '');
}

String _appPos(String packPos, String fallback) => switch (packPos) {
      'noun' || 'verb' || 'phrase' => packPos,
      'adj' => 'adj.',
      'adv' => 'adv.',
      _ => fallback,
    };

/// Adds what the learner confirmed; returns (added, skipped).
({int added, int skipped}) addBulkItems(
    WordDatabaseRepository repo, List<BulkItem> items) {
  var added = 0, skipped = 0;
  for (final i in items) {
    if (!i.willAdd) {
      skipped++;
      continue;
    }
    try {
      repo.addWord(
          word: i.target,
          pos: i.pos,
          meaning: i.status == BulkStatus.variant && i.keepTyped
              ? ''
              : i.meaning,
          // The level stays the dictionary's (a given level is marked "user").
          level: null);
      added++;
    } on DuplicateWordException {
      skipped++;
    }
  }
  return (added: added, skipped: skipped);
}
