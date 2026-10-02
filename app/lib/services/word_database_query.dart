import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import 'lexicon_pack.dart';

enum SortOrder {
  alphabetical('字母 A–Z'),
  recentlyUpdated('最近更新'),
  nextDue('下次出現');

  final String label;
  const SortOrder(this.label);
}

/// The 狀態 column. FSRS itself only knows New / Learning / Review /
/// Relearning; 複習中 vs 穩定 splits Review at [stableStabilityDays], the
/// same 21-day line Anki uses for "mature" cards.
enum StudyStatus {
  newWord('新單字'),
  learning('學習中'),
  reviewing('複習中'),
  stable('穩定'),

  /// Swiped away as known — the card is archived (spec: 已學會).
  learned('已學會'),

  /// Added by hand, no card yet.
  noCard('未建卡');

  final String label;
  const StudyStatus(this.label);

  static const stableStabilityDays = 21.0;

  static StudyStatus of(LearningCard? card) {
    if (card == null) return StudyStatus.noCard;
    if (card.archived) return StudyStatus.learned;
    return switch (card.fsrs.state) {
      FsrsCardState.newCard => StudyStatus.newWord,
      FsrsCardState.learning ||
      FsrsCardState.relearning =>
        StudyStatus.learning,
      FsrsCardState.review => card.fsrs.stability >= stableStabilityDays
          ? StudyStatus.stable
          : StudyStatus.reviewing,
    };
  }
}

/// The 缺漏欄位 filter.
enum MissingField {
  ipa('缺音標'),
  example('缺例句'),
  exampleTranslation('缺例句翻譯'),
  related('缺相關詞彙'),
  failed('資料取得失敗');

  final String label;
  const MissingField(this.label);

  bool isMissingIn(WordEntry e) => switch (this) {
        MissingField.ipa => e.ipa == null,
        MissingField.example => e.examples.isEmpty,
        MissingField.exampleTranslation =>
          e.examples.any((x) => (x.translation ?? '').isEmpty),
        MissingField.related => e.related.isEmpty,
        MissingField.failed => e.dataStatus == WordDataStatus.failed,
      };
}

/// "下次出現" wording. Overdue cards read 今天, never "逾期 N 天" — spec
/// section 4: no 欠卡 counts or pressure.
String dueLabel(LearningCard? card, DateTime now) {
  if (card == null) return '尚未開始';
  if (card.archived) return '—';
  final due = card.fsrs.due;
  if (due == null || card.fsrs.state == FsrsCardState.newCard) return '尚未開始';
  final days = DateTime(due.year, due.month, due.day)
      .difference(DateTime(now.year, now.month, now.day))
      .inDays;
  if (days <= 0) return '今天';
  if (days == 1) return '明天';
  return '$days 天後';
}

/// 1284 → "1,284".
String formatCount(int n) {
  final digits = n.abs().toString();
  final out = StringBuffer(n < 0 ? '-' : '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write(',');
    out.write(digits[i]);
  }
  return out.toString();
}

/// The word list's search and filters. Spec section 7: 手機單字集以
/// WordEntry 為一列…預設依字母排列並提供搜尋.
class WordDatabaseFilter {
  final String search;

  /// Album id.
  final String? album;
  final String? pos;

  /// CEFR level (等級篩選).
  final String? level;
  final StudyStatus? status;
  final MissingField? missing;
  final SortOrder sort;

  const WordDatabaseFilter({
    this.search = '',
    this.album,
    this.pos,
    this.level,
    this.status,
    this.missing,
    this.sort = SortOrder.alphabetical,
  });

  /// Nullable filters use a function so callers can clear them back to
  /// "全部" (`album: () => null`).
  WordDatabaseFilter copyWith({
    String? search,
    String? Function()? album,
    String? Function()? pos,
    String? Function()? level,
    StudyStatus? Function()? status,
    MissingField? Function()? missing,
    SortOrder? sort,
  }) =>
      WordDatabaseFilter(
        search: search ?? this.search,
        album: album != null ? album() : this.album,
        pos: pos != null ? pos() : this.pos,
        level: level != null ? level() : this.level,
        status: status != null ? status() : this.status,
        missing: missing != null ? missing() : this.missing,
        sort: sort ?? this.sort,
      );
}

/// One row: a WordEntry and its one card.
class DatabaseRow {
  final String id;
  final WordEntry entry;
  final LearningCard? card;
  final int photoCount;
  final StudyStatus status;

  const DatabaseRow({
    required this.id,
    required this.entry,
    required this.card,
    required this.photoCount,
    required this.status,
  });
}

class PageSlice<T> {
  final List<T> items;
  final int page;
  final int pageCount;
  final int total;

  /// 1-based index of the first item on this page (0 when empty).
  final int start;
  final int end;

  const PageSlice({
    required this.items,
    required this.page,
    required this.pageCount,
    required this.total,
    required this.start,
    required this.end,
  });

  /// Clamps [page] into range, so shrinking a result set (e.g. typing a
  /// search) never strands the user on an empty page.
  factory PageSlice.of(List<T> all, int page, int pageSize) {
    final pageCount = all.isEmpty ? 1 : (all.length / pageSize).ceil();
    final p = page.clamp(0, pageCount - 1);
    final from = p * pageSize;
    final to = (from + pageSize).clamp(0, all.length);
    return PageSlice(
      items: all.sublist(from, to),
      page: p,
      pageCount: pageCount,
      total: all.length,
      start: all.isEmpty ? 0 : from + 1,
      end: to,
    );
  }
}

/// Which page numbers the footer shows: all of them when there are at
/// most [size], otherwise a [size]-wide window around [page].
List<int> pageWindow(int page, int pageCount, {int size = 3}) {
  if (pageCount <= size) return [for (var i = 0; i < pageCount; i++) i];
  final start = (page - size ~/ 2).clamp(0, pageCount - size);
  return [for (var i = 0; i < size; i++) start + i];
}

/// The fields a word still lacks, by name (spec section 7: 單字集必須指出
/// 發音、例句、詞源、翻譯等具體失敗欄位，不可只顯示整個詞條錯誤).
List<String> missingFieldNames(WordEntry e) => [
      if (e.meaning.trim().isEmpty) '中文意思',
      if (e.ipa == null) '音標',
      if (e.audioUrl == null) '真人發音',
      if (e.examples.isEmpty) '例句',
      if (e.examples.isNotEmpty &&
          e.examples.every((x) => (x.translation ?? '').trim().isEmpty))
        '例句翻譯',
      // The admin's field status: the origin is known to exist but has not
      // been fetched or translated yet.
      if (LexiconPack.instance.lookup(e.word, pos: e.pos)?.entry.missing.keys
              .any((f) => f.startsWith('etymology')) ??
          false)
        '詞源',
    ];

bool matchesSearch(String query, WordEntry e, Iterable<Photo> photos) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return true;
  final haystack = <String?>[
    e.word,
    e.pos,
    e.meaning,
    e.definition,
    e.definitionEn,
    e.ipa,
    e.level,
    ...e.tags,
    for (final x in e.examples) ...[x.text, x.translation],
    for (final r in e.related) r.word,
    for (final p in photos) ...[p.title, p.place],
  ];
  return haystack.any((s) => s != null && s.toLowerCase().contains(q));
}

int compareRows(SortOrder sort, DatabaseRow a, DatabaseRow b) {
  switch (sort) {
    case SortOrder.alphabetical:
      final c = a.entry.word.compareTo(b.entry.word);
      return c != 0 ? c : a.id.compareTo(b.id);
    case SortOrder.recentlyUpdated:
      final c = b.entry.updatedAt.compareTo(a.entry.updatedAt);
      return c != 0 ? c : a.id.compareTo(b.id);
    case SortOrder.nextDue:
      final ad = a.card == null || a.card!.archived ? null : a.card!.fsrs.due;
      final bd = b.card == null || b.card!.archived ? null : b.card!.fsrs.due;
      if (ad == null && bd != null) return 1;
      if (bd == null && ad != null) return -1;
      final c = ad == null ? 0 : ad.compareTo(bd!);
      return c != 0 ? c : a.entry.word.compareTo(b.entry.word);
  }
}
