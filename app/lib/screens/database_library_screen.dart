import '../l10n/ui_text.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/dictionary_sync.dart';
import '../services/learning_content.dart';
import '../services/license_links.dart';
import '../services/lexicon_pack.dart';
import '../services/pack_media.dart';
import '../services/word_database_repository.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'album_screen.dart';
import 'word_database_screen.dart';

part '../widgets/database_image_data.dart';
part '../widgets/database_image_views.dart';
part '../widgets/database_word_detail.dart';
part '../widgets/database_tag_sections.dart';

/// Database views are projections of the server snapshot, not copies mixed
/// into personal learning records. Removing a database item removes it here.
class DatabaseLibraryScreen extends StatefulWidget {
  final bool photos;
  const DatabaseLibraryScreen({super.key, required this.photos});
  @override
  State<DatabaseLibraryScreen> createState() => _DatabaseLibraryScreenState();
}

class _DatabaseLibraryScreenState extends State<DatabaseLibraryScreen> {
  bool _personal = false;
  bool _includeIncomplete = false;
  String _search = '';
  final _searchController = TextEditingController();

  /// The 相片冊's 標籤程度 picker; null shows every level.
  String? _level;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: MColors.canvas,
        body: SafeArea(
            bottom: false,
            child: Column(children: [
              Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: MSpace.md, vertical: MSpace.xs),
                  child: Wrap(runSpacing: MSpace.xs, children: [
                    // The app's own pill, not ChoiceChip: on the web the
                    // chip measured Chinese too narrow (問題回報 #37:
                    // 「資料庫」 showed as 「資」).
                    _SourcePill(
                        label: '資料庫',
                        selected: !_personal,
                        onTap: () => setState(() => _personal = false)),
                    const SizedBox(width: MSpace.xs),
                    _SourcePill(
                        label: widget.photos ? '我的相片冊' : '我的單字本',
                        selected: _personal,
                        onTap: () => setState(() => _personal = true)),
                  ])),
              Expanded(
                  child: _personal
                      ? (widget.photos
                          ? AlbumScreen(
                              onBack: () => setState(() => _personal = false))
                          : WordDatabaseScreen(
                              onBack: () => setState(() => _personal = false)))
                      : ListenableBuilder(
                          listenable: Listenable.merge(
                              [LexiconPack.instance, DictionarySync.instance]),
                          builder: (context, _) {
                            final pack = LexiconPack.instance;
                            if (!pack.hasCatalog) {
                              return Center(
                                  child: Padding(
                                      padding: const EdgeInsets.all(MSpace.xl),
                                      child: Container(
                                        padding:
                                            const EdgeInsets.all(MSpace.lg),
                                        decoration: MDecor.emptyStateCard(),
                                        child: Column(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              const CircularProgressIndicator(
                                                  color: MColors.primary),
                                              const SizedBox(height: MSpace.md),
                                              UiText('正在取得資料庫內容',
                                                  style: MFont.titleSm),
                                              const SizedBox(height: MSpace.xs),
                                              Text(
                                                  DictionarySync
                                                      .instance.status,
                                                  textAlign: TextAlign.center,
                                                  style: MFont.bodyMuted),
                                              const SizedBox(height: MSpace.md),
                                              ElevatedButton(
                                                  onPressed: DictionarySync
                                                      .instance.refresh,
                                                  child: const UiText('重新連線')),
                                            ]),
                                      )));
                            }
                            final allWords = pack.catalogWords;
                            final words = allWords
                                .where((w) =>
                                    (_includeIncomplete || w.full) &&
                                    w.searchText
                                        .contains(_search.toLowerCase()))
                                .toList()
                              // Rarer parts of speech after the main ones
                              // (問題回報 #16).
                              ..sort((a, b) => a.rareUsage != b.rareUsage
                                  ? (a.rareUsage ? 1 : -1)
                                  : a.lemma.compareTo(b.lemma));
                            // A chosen level shows only pictures with at least
                            // one drawable pin at that level. An approved word
                            // without model coordinates is metadata, not a
                            // visible photo label (問題回報 #143).
                            final images = pack.catalogImages
                                .where((image) =>
                                    databaseImageLabels(image, pack)
                                        .toLowerCase()
                                        .contains(_search.toLowerCase()) &&
                                    (_level == null ||
                                        databasePins(image, pack,
                                                max: 1, level: _level)
                                            .isNotEmpty))
                                .toList();
                            return Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Padding(
                                      padding: const EdgeInsets.fromLTRB(
                                          MSpace.md, 4, MSpace.md, MSpace.sm),
                                      child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            UiText(
                                                widget.photos
                                                    ? '資料庫相片冊'
                                                    : '資料庫單字本',
                                                style: MFont.display),
                                            const SizedBox(height: 4),
                                            UiText(
                                                widget.photos
                                                    ? _level == null
                                                        ? '共 ${pack.catalogImages.length} 張圖片 · 每張都有單字標籤'
                                                        : '${levelLabel(_level!)}：${images.length} 張圖片有這個程度的標籤'
                                                    : '${allWords.where((w) => w.full).length} 筆正式單字 · 與資料庫同步',
                                                style: MFont.bodyMuted),
                                            // Connecting/connected is debug
                                            // chrome, not learner-facing info;
                                            // only the failure message is
                                            // worth a permanent line (問題回報 #260).
                                            if (DictionarySync
                                                .instance.hasError) ...[
                                              const SizedBox(height: 2),
                                              UiText(
                                                  DictionarySync
                                                      .instance.status,
                                                  style: MFont.caption),
                                            ],
                                            const SizedBox(height: MSpace.sm),
                                            TextField(
                                                controller: _searchController,
                                                onChanged: (value) => setState(
                                                    () => _search = value),
                                                decoration: InputDecoration(
                                                    prefixIcon: const Icon(
                                                        Icons.search,
                                                        color: MColors.muted),
                                                    hintText: ui(context, widget.photos
                                                        ? '搜尋圖片上的英文或中文標籤'
                                                        : '搜尋英文或中文'),
                                                    hintStyle:
                                                        MFont.bodyMuted)),
                                            if (widget.photos) ...[
                                              const SizedBox(height: MSpace.sm),
                                              LabelLevelBar(
                                                  level: _level,
                                                  defaultLabel: '全部',
                                                  onChanged: (l) => setState(
                                                      () => _level = l)),
                                            ],
                                            // Stubs in the pack are form
                                            // pointers (tore → tear), not list
                                            // rows: a 「（0）」 box does nothing.
                                            if (!widget.photos &&
                                                allWords.any((w) => !w.full))
                                              CheckboxListTile(
                                                  contentPadding:
                                                      EdgeInsets.zero,
                                                  title: UiText(
                                                      '包含待補齊單字（${allWords.where((w) => !w.full).length}）',
                                                      style: MFont.manrope(
                                                          13,
                                                          FontWeight.w600,
                                                          MColors.ink)),
                                                  value: _includeIncomplete,
                                                  activeColor: MColors.primary,
                                                  onChanged: (value) =>
                                                      setState(() =>
                                                          _includeIncomplete =
                                                              value ?? false)),
                                          ])),
                                  Expanded(
                                      child: widget.photos
                                          ? images.isEmpty
                                              ? Center(
                                                  child: Container(
                                                    margin:
                                                        const EdgeInsets.all(
                                                            MSpace.lg),
                                                    padding:
                                                        const EdgeInsets.all(
                                                            MSpace.xl),
                                                    decoration:
                                                        MDecor.emptyStateCard(),
                                                    child: UiText('沒有符合的圖片',
                                                        style: MFont.bodyMuted),
                                                  ),
                                                )
                                              : GridView.builder(
                                                  padding: const EdgeInsets.all(
                                                      MSpace.md),
                                                  itemCount: images.length,
                                                  gridDelegate:
                                                      const SliverGridDelegateWithFixedCrossAxisCount(
                                                          crossAxisCount: 2,
                                                          mainAxisExtent: 230,
                                                          mainAxisSpacing:
                                                              MSpace.sm,
                                                          crossAxisSpacing:
                                                              MSpace.sm),
                                                  itemBuilder: (context,
                                                          index) =>
                                                      DatabaseImageTile(
                                                          image: images[index],
                                                          level: _level))
                                          : words.isEmpty
                                              ? Center(
                                                  child: Container(
                                                    margin:
                                                        const EdgeInsets.all(
                                                            MSpace.lg),
                                                    padding:
                                                        const EdgeInsets.all(
                                                            MSpace.xl),
                                                    decoration:
                                                        MDecor.emptyStateCard(),
                                                    child: UiText('沒有符合的單字',
                                                        style: MFont.bodyMuted),
                                                  ),
                                                )
                                              : ListView.separated(
                                                  padding:
                                                      const EdgeInsets.symmetric(
                                                          horizontal: MSpace.md,
                                                          vertical: MSpace.xs),
                                                  itemCount: words.length,
                                                  separatorBuilder: (context,
                                                          index) =>
                                                      const SizedBox(
                                                          height: MSpace.xxs),
                                                  itemBuilder: (context, index) {
                                                    final word = words[index];
                                                    return Container(
                                                      decoration: MDecor
                                                          .listTileSurface(
                                                              showDivider:
                                                                  false),
                                                      child: InkWell(
                                                        onTap: () =>
                                                            openDatabaseWord(
                                                                context,
                                                                word.id),
                                                        borderRadius:
                                                            BorderRadius
                                                                .circular(
                                                                    MRadii.sm),
                                                        child: Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .symmetric(
                                                                  horizontal:
                                                                      MSpace.md,
                                                                  vertical:
                                                                      MSpace
                                                                          .sm),
                                                          child: Row(
                                                            children: [
                                                              Expanded(
                                                                child: Column(
                                                                  crossAxisAlignment:
                                                                      CrossAxisAlignment
                                                                          .start,
                                                                  children: [
                                                                    Text(
                                                                        word
                                                                            .lemma,
                                                                        style: MFont.manrope(
                                                                            16,
                                                                            FontWeight.w800,
                                                                            MColors.ink)),
                                                                    const SizedBox(
                                                                        height:
                                                                            2),
                                                                    Text(
                                                                        '${word.learnerMeaning ?? ui(context, '中文意思待補齊')}\n${[
                                                                          if (word.entryType !=
                                                                              'word')
                                                                            entryTypeLabel(word.entryType),
                                                                          posLabel(
                                                                              word.pos)
                                                                        ].join(' / ')}'
                                                                        '${word.cefr == null ? '' : ' · ${levelText(word.cefr!, estimated: word.cefrEstimated)}'}'
                                                                        '${word.rareUsage ? ' · 罕見用法' : ''}',
                                                                        style: MFont.manrope(
                                                                            13,
                                                                            FontWeight.w500,
                                                                            MColors.muted)),
                                                                  ],
                                                                ),
                                                              ),
                                                              const Icon(
                                                                  Icons
                                                                      .chevron_right,
                                                                  color: MColors
                                                                      .muted),
                                                            ],
                                                          ),
                                                        ),
                                                      ),
                                                    );
                                                  })),
                                ]);
                          })),
            ])),
      );
}

class _SourcePill extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _SourcePill(
      {required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) => Semantics(
        selected: selected,
        child: Tap(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: MSpace.md, vertical: MSpace.xs),
            decoration: MDecor.chipSurface(active: selected),
            child: UiText(label,
                style: MFont.manrope(14, FontWeight.w700,
                    selected ? MColors.primaryDeep : MColors.ink)),
          ),
        ),
      );
}
