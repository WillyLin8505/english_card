import '../models/learning_card.dart' show LabelPoint;
import '../models/word_candidate.dart';
import '../models/word_entry.dart' show cefrLevels;

/// 照片詳情「詞性 × CEFR」表格 (M180, owner #732): the photo's words by
/// part of speech (rows) and level (columns).
///
/// Today the grid is filled from the photo's own words (its candidates and
/// its listed labels, each with a pos and a CEFR level). Later the server
/// (Windows #731) returns a grid per photo where one tag — one concept at
/// one spot — has words from easy to hard (happy A1 → joyful B2 → elated
/// C1); those come in as [GridWord]s sharing a [GridWord.tagId] and
/// [GridWord.point], and go through the same [buildPhotoWordGrid].
enum GridRow { verb, noun, adjective, adverb, phrase }

/// The row's heading (UiText source key, already in the catalog).
String gridRowLabel(GridRow r) => switch (r) {
      GridRow.verb => '動詞',
      GridRow.noun => '名詞',
      GridRow.adjective => '形容詞',
      GridRow.adverb => '副詞',
      GridRow.phrase => '片語',
    };

/// One word in a cell.
class GridWord {
  final String word;
  final String pos;

  /// CEFR, A1–C2.
  final String level;
  final String meaning;

  /// The tag (concept + spot on the photo) this word belongs to, so words
  /// of one concept can share a point; null when unknown.
  final String? tagId;
  final LabelPoint? point;

  /// The photo candidate it came from, when it came from one (used to add
  /// the word to the photo's list).
  final WordCandidate? candidate;

  const GridWord({
    required this.word,
    required this.pos,
    required this.level,
    this.meaning = '',
    this.tagId,
    this.point,
    this.candidate,
  });

  factory GridWord.fromCandidate(WordCandidate c, {String? tagId}) => GridWord(
        word: c.word,
        pos: c.pos,
        level: c.level,
        meaning: c.meaning,
        tagId: tagId ?? c.word,
        point: c.point,
        candidate: c,
      );
}

/// The row a pack / app part of speech goes to; anything else is a
/// phrase when it is several words, otherwise skipped (null).
GridRow? gridRowFor(String pos, String word) {
  final p = pos.trim().toLowerCase().replaceAll('.', '');
  switch (p) {
    case 'verb' ||
          'v' ||
          'vt' ||
          'vi' ||
          'aux' ||
          'auxiliary verb' ||
          'modal verb' ||
          'modal':
      return GridRow.verb;
    case 'noun' || 'n' || 'proper noun':
      return GridRow.noun;
    case 'adj' || 'adjective' || 'a':
      return GridRow.adjective;
    case 'adv' || 'adverb':
      return GridRow.adverb;
    case 'phrase' ||
          'phrasal verb' ||
          'phrasal' ||
          'idiom' ||
          'expression' ||
          'collocation' ||
          'phr v' ||
          'phrv':
      return GridRow.phrase;
  }
  return word.trim().contains(' ') ? GridRow.phrase : null;
}

/// The 5 × 6 table: [cells] by row, then by level index (0 = A1).
class PhotoWordGrid {
  final Map<GridRow, List<List<GridWord>>> cells;

  const PhotoWordGrid(this.cells);

  List<GridWord> cell(GridRow row, int level) => cells[row]![level];

  bool get isEmpty =>
      cells.values.every((levels) => levels.every((c) => c.isEmpty));
}

/// Groups [words] into the grid: each word once (first one wins), in a
/// cell by [gridRowFor] and its CEFR level; unknown levels and parts of
/// speech that fit no row are left out. Within a cell words keep their
/// order.
PhotoWordGrid buildPhotoWordGrid(Iterable<GridWord> words) {
  final cells = {
    for (final r in GridRow.values)
      r: List.generate(cefrLevels.length, (_) => <GridWord>[]),
  };
  final seen = <String>{};
  for (final w in words) {
    final key = w.word.trim().toLowerCase();
    if (key.isEmpty || !seen.add(key)) continue;
    final row = gridRowFor(w.pos, w.word);
    final level = cefrLevels.indexOf(w.level.trim().toUpperCase());
    if (row == null || level < 0) continue;
    cells[row]![level].add(w);
  }
  return PhotoWordGrid(cells);
}
