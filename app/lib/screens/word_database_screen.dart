import '../services/learning_content.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../models/word_entry.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';

/// 單字資料庫 — Figma "Word Database · Mobile" (35:2), the 單字本 tab.
/// Spec section 7 (單字集與資料狀態): one row per WordEntry — the same
/// word shows once however many photos it is in — in alphabetical order,
/// with search; tap a row for its photos, card, review log and FSRS
/// changes. A word whose background data fetch failed is marked.
class WordDatabaseScreen extends StatefulWidget {
  const WordDatabaseScreen({super.key});

  @override
  State<WordDatabaseScreen> createState() => _WordDatabaseScreenState();
}

class _WordDatabaseScreenState extends State<WordDatabaseScreen> {
  static const _pageSize = 8;

  final _search = TextEditingController();
  WordDatabaseFilter _filter = const WordDatabaseFilter();
  int _page = 0;
  bool _onlyLearning = false;
  final Set<String> _selected = {};

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _setFilter(WordDatabaseFilter f) => setState(() {
        _filter = f;
        _page = 0;
      });

  Future<void> _addWord() async {
    final scope = AppScope.of(context);
    final entry = await showAddWordDialog(context, scope.repository);
    if (entry == null || !mounted) return;
    _search.clear();
    setState(() {
      _filter = WordDatabaseFilter(sort: _filter.sort);
      _page = 0;
      _selected
        ..clear()
        ..add(entry.id);
    });
    unawaited(scope.enricher.process());
    showToast(context, '已新增「${entry.word}」，例句與翻譯會在背景補上。');
  }

  void _share(List<DatabaseRow> rows) {
    final lines = [
      for (final r in rows)
        [
          r.entry.word,
          r.entry.meaning,
          if (r.entry.level != null) r.entry.level
        ].join('　'),
    ];
    SharePlus.instance.share(ShareParams(
      title: '我的單字本',
      text: '我的單字本（${rows.length}）\n${lines.join('\n')}',
    ));
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final rows = repo
            .query(_filter)
            .where((r) =>
                !_onlyLearning ||
                (r.status != StudyStatus.learned &&
                    r.status != StudyStatus.noCard))
            .toList();
        final slice = PageSlice.of(rows, _page, _pageSize);
        _selected.removeWhere((id) => !rows.any((r) => r.id == id));

        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                MNavBar(
                  title: '我的單字本',
                  leading: BackNavButton(
                    onTap: () => Navigator.of(context).canPop()
                        ? Navigator.of(context).pop()
                        : scope.navigator.selectTab(AppTab.camera),
                  ),
                  trailing: ShareNavButton(onTap: () => _share(rows)),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(MSpace.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SdsSearchField(
                          controller: _search,
                          onChanged: (t) =>
                              _setFilter(_filter.copyWith(search: t)),
                        ),
                        const SizedBox(height: MSpace.sm),
                        Row(
                          children: [
                            Expanded(
                              child: Tap(
                                onTap: _addWord,
                                label: '新增單字',
                                child: Container(
                                  height: 44,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: MSpace.md),
                                  decoration:
                                      MDecor.primaryPill(radius: MRadii.md),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      const Icon(Icons.add_rounded,
                                          color: Colors.white, size: 18),
                                      const SizedBox(width: MSpace.xxs),
                                      Text('新增單字',
                                          style: MFont.manrope(
                                              14, FontWeight.w700, Colors.white)),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: MSpace.xs),
                            Expanded(
                              child: Tap(
                                onTap: () =>
                                    scope.navigator.selectTab(AppTab.review),
                                label: '開始複習',
                                child: Container(
                                  height: 44,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: MSpace.md),
                                  decoration: MDecor.card(
                                    color: MColors.surface,
                                    borderColor: MColors.border,
                                    radius: MRadii.md,
                                    shadow: MShadows.soft,
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      const Icon(Icons.school_rounded,
                                          color: MColors.primary, size: 18),
                                      const SizedBox(width: MSpace.xxs),
                                      Text('開始複習',
                                          style: MFont.manrope(
                                              14, FontWeight.w700, MColors.primary)),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: MSpace.sm),
                        Wrap(
                          spacing: MSpace.xs,
                          runSpacing: MSpace.xs,
                          children: [
                            for (final label in ['全部', '還在學', '已學會'])
                              (() {
                                final isSelected = label == '還在學'
                                    ? _onlyLearning
                                    : !_onlyLearning &&
                                        (label == '全部'
                                            ? _filter.status == null
                                            : _filter.status ==
                                                StudyStatus.learned);
                                return Tap(
                                  onTap: () {
                                    setState(() {
                                      _onlyLearning = label == '還在學';
                                      _filter = _filter.copyWith(
                                          status: () => label == '已學會'
                                              ? StudyStatus.learned
                                              : null);
                                      _page = 0;
                                    });
                                  },
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: MSpace.md,
                                        vertical: MSpace.xs),
                                    decoration:
                                        MDecor.chipSurface(active: isSelected),
                                    child: Text(
                                      label,
                                      style: MFont.manrope(
                                        13,
                                        FontWeight.w700,
                                        isSelected
                                            ? MColors.primaryDeep
                                            : MColors.ink,
                                      ),
                                    ),
                                  ),
                                );
                              })(),
                          ],
                        ),
                        const SizedBox(height: MSpace.sm),
                        Container(
                          decoration: MDecor.softPanel(
                            color: MColors.surfaceSoft,
                            radius: MRadii.md,
                          ),
                          clipBehavior: Clip.antiAlias,
                          child: Material(
                            color: Colors.transparent,
                            child: ExpansionTile(
                                title: Text('進階篩選與排序',
                                    style: MFont.manrope(
                                        14, FontWeight.w700, MColors.ink)),
                                collapsedBackgroundColor: Colors.transparent,
                                backgroundColor: MColors.surface,
                                shape: const Border(),
                                collapsedShape: const Border(),
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.all(MSpace.md),
                                    child: _buildFilters(repo.partsOfSpeech),
                                  ),
                                ]),
                          ),
                        ),
                        const SizedBox(height: MSpace.md),
                        _buildTable(slice),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFilters(List<String> partsOfSpeech) {
    final f = _filter;
    return Wrap(
      spacing: MSpace.xs,
      runSpacing: MSpace.xs,
      children: [
        MenuPill<String>(
          label: f.pos != null ? posLabel(f.pos!) : '全部詞性',
          active: f.pos != null,
          selected: f.pos,
          options: [
            (null, '全部詞性'),
            for (final p in partsOfSpeech) (p, posLabel(p))
          ],
          onSelected: (v) => _setFilter(f.copyWith(pos: () => v)),
        ),
        MenuPill<StudyStatus>(
          label: f.status?.label ?? '學習狀態',
          active: f.status != null,
          selected: f.status,
          options: [
            (null, '全部狀態'),
            for (final s in StudyStatus.values) (s, s.label)
          ],
          onSelected: (v) => _setFilter(f.copyWith(status: () => v)),
        ),
        MenuPill<String>(
          label: f.level ?? '等級篩選',
          active: f.level != null,
          selected: f.level,
          options: [
            (null, '全部等級'),
            for (final l in cefrLevels) (l, levelLabel(l))
          ],
          onSelected: (v) => _setFilter(f.copyWith(level: () => v)),
        ),
        MenuPill<MissingField>(
          label: f.missing?.label ?? '缺漏欄位',
          active: f.missing != null,
          selected: f.missing,
          options: [
            (null, '不限'),
            for (final m in MissingField.values) (m, m.label)
          ],
          onSelected: (v) => _setFilter(f.copyWith(missing: () => v)),
        ),
        MenuPill<SortOrder>(
          label: f.sort.label,
          active: f.sort != SortOrder.alphabetical,
          selected: f.sort,
          options: [for (final s in SortOrder.values) (s, s.label)],
          onSelected: (v) {
            if (v != null) _setFilter(f.copyWith(sort: v));
          },
        ),
      ],
    );
  }

  Widget _buildTable(PageSlice<DatabaseRow> slice) {
    final scope = AppScope.of(context);
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: MDecor.card(radius: MRadii.lg),
      child: Column(
        children: [
          if (slice.items.isEmpty)
            Container(
              padding: const EdgeInsets.symmetric(
                  vertical: MSpace.xxl * 1.5, horizontal: MSpace.lg),
              alignment: Alignment.center,
              decoration: MDecor.emptyStateCard(),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(MSpace.md),
                    decoration: const BoxDecoration(
                      color: MColors.primarySoft,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.search_off_rounded,
                        size: 32, color: MColors.primary),
                  ),
                  const SizedBox(height: MSpace.md),
                  Text('沒有符合條件的單字',
                      style: MFont.titleSm.copyWith(color: MColors.ink)),
                  const SizedBox(height: MSpace.xxs),
                  Text('請嘗試調整搜尋關鍵字或進階篩選條件',
                      style: MFont.bodyMuted),
                ],
              ),
            ),
          for (final row in slice.items)
            _WordRow(
              key: ValueKey(row.id),
              word: row.entry.word,
              meaning: row.entry.meaning,
              level: row.entry.level,
              learned: row.status == StudyStatus.learned,
              dataFailed: row.entry.dataStatus == WordDataStatus.failed,
              missing: missingFieldNames(row.entry),
              selected: _selected.contains(row.id),
              onTap: () {
                setState(() {
                  _selected
                    ..clear()
                    ..add(row.id);
                });
                scope.navigator.openWord(row.entry.id);
              },
              onToggle: () => scope.speaker.say(row.entry.word,
                  language: scope.repository.language,
                  audioUrl: row.entry.audioUrl),
            ),
          _buildFooter(slice),
        ],
      ),
    );
  }

  Widget _buildFooter(PageSlice<DatabaseRow> slice) {
    final range = slice.total == 0 ? '0' : '${slice.start}-${slice.end}';
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: MSpace.md),
      decoration:
          MDecor.listTileSurface(color: MColors.surfaceSoft, showDivider: true),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '第 $range 個，共 ${formatCount(slice.total)} 個',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: MFont.inter(12, FontWeight.w500, MColors.muted,
                  height: 1.4),
            ),
          ),
          FilterPill(
            label: '‹',
            onTap: slice.page > 0
                ? () => setState(() => _page = slice.page - 1)
                : null,
          ),
          for (final p in pageWindow(slice.page, slice.pageCount)) ...[
            const SizedBox(width: MSpace.xxs),
            FilterPill(
              label: '${p + 1}',
              active: p == slice.page,
              onTap: () => setState(() => _page = p),
            ),
          ],
          const SizedBox(width: MSpace.xxs),
          FilterPill(
            label: '›',
            onTap: slice.page < slice.pageCount - 1
                ? () => setState(() => _page = slice.page + 1)
                : null,
          ),
        ],
      ),
    );
  }
}

/// Figma "word-row" (54:436): 62px, marker / word / meaning / level.
class _WordRow extends StatelessWidget {
  final String word;
  final String meaning;
  final String? level;
  final bool learned;
  final bool dataFailed;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onToggle;

  const _WordRow({
    super.key,
    required this.word,
    required this.meaning,
    required this.level,
    this.learned = false,
    this.dataFailed = false,
    required this.selected,
    required this.onTap,
    required this.onToggle,
    this.missing = const [],
  });

  /// The fields still missing, named (spec: 具體失敗欄位).
  final List<String> missing;

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: '$word，$meaning',
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: MSpace.md, vertical: MSpace.sm + 2),
          decoration: MDecor.listTileSurface(
            color: selected ? MColors.primarySoft : MColors.surface,
            showDivider: true,
          ),
          child: Row(children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(word,
                      style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                  const SizedBox(height: MSpace.xxs),
                  Text(
                    meaning.isEmpty ? '中文意思尚未補齊' : meaning,
                    style: MFont.manrope(
                      14,
                      FontWeight.w600,
                      meaning.isEmpty ? MColors.muted : MColors.primary,
                    ),
                  ),
                  if (dataFailed)
                    Padding(
                      padding: const EdgeInsets.only(top: MSpace.xxs),
                      child: Tooltip(
                        message: '資料取得失敗，稍後自動重試',
                        child: Text(
                          missing.isEmpty
                              ? '部分內容待補齊'
                              : '待補：${missing.join('、')}',
                          style: MFont.manrope(
                              12, FontWeight.w600, MColors.label),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            if (learned)
              const Padding(
                padding: EdgeInsets.only(right: MSpace.xs),
                child: Icon(Icons.check_circle,
                    color: MColors.success, size: 18),
              ),
            if (level != null) ...[
              LevelBadge(level!),
              const SizedBox(width: MSpace.xxs),
            ],
            IconButton(
              tooltip: '聽 $word 的發音',
              onPressed: onToggle,
              icon: const Icon(Icons.volume_up_outlined,
                  color: MColors.primary, size: 20),
            ),
          ]),
        ),
      );
}
