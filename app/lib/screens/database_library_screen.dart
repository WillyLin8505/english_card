import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/dictionary_sync.dart';
import '../services/learning_content.dart';
import '../services/lexicon_pack.dart';
import '../services/word_database_repository.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'album_screen.dart';
import 'word_database_screen.dart';

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

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: MColors.canvas,
        body: SafeArea(
            bottom: false,
            child: Column(children: [
              Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: MSpace.md, vertical: MSpace.xs),
                  child: Row(children: [
                    // The app's own pill, not ChoiceChip: on the web the
                    // chip measured Chinese too narrow (問題回報 #37:
                    // 「資料庫」 showed as 「資」).
                    _SourcePill(
                        label: '資料庫',
                        selected: !_personal,
                        onTap: () => setState(() => _personal = false)),
                    const SizedBox(width: MSpace.xs),
                    _SourcePill(
                        label: '我的收藏',
                        selected: _personal,
                        onTap: () => setState(() => _personal = true)),
                  ])),
              Expanded(
                  child: _personal
                      ? (widget.photos
                          ? const AlbumScreen()
                          : const WordDatabaseScreen())
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
                                              Text('正在取得資料庫內容',
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
                                                  child: const Text('重新連線')),
                                            ]),
                                      )));
                            }
                            final allWords = pack.catalogWords;
                            final words = allWords
                                .where((w) =>
                                    (_includeIncomplete || w.full) &&
                                    '${w.lemma} ${w.learnerMeaning ?? ''}'
                                        .toLowerCase()
                                        .contains(_search.toLowerCase()))
                                .toList()
                              // Rarer parts of speech after the main ones
                              // (問題回報 #16).
                              ..sort((a, b) => a.rareUsage != b.rareUsage
                                  ? (a.rareUsage ? 1 : -1)
                                  : a.lemma.compareTo(b.lemma));
                            final images = pack.catalogImages
                                .where((image) =>
                                    databaseImageLabels(image, pack)
                                        .toLowerCase()
                                        .contains(_search.toLowerCase()))
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
                                            Text(
                                                widget.photos
                                                    ? '資料庫相片冊'
                                                    : '資料庫單字本',
                                                style: MFont.display),
                                            const SizedBox(height: 4),
                                            Text(
                                                widget.photos
                                                    ? '共 ${pack.catalogImages.length} 張圖片 · 每張都有單字標籤'
                                                    : '${allWords.where((w) => w.full).length} 筆正式單字 · 與資料庫同步',
                                                style: MFont.bodyMuted),
                                            const SizedBox(height: 2),
                                            Text(DictionarySync.instance.status,
                                                style: MFont.caption),
                                            const SizedBox(height: MSpace.sm),
                                            TextField(
                                                onChanged: (value) => setState(
                                                    () => _search = value),
                                                decoration: InputDecoration(
                                                    prefixIcon: const Icon(
                                                        Icons.search,
                                                        color: MColors.muted),
                                                    hintText: widget.photos
                                                        ? '搜尋圖片上的英文或中文標籤'
                                                        : '搜尋英文或中文',
                                                    hintStyle:
                                                        MFont.bodyMuted)),
                                            if (!widget.photos)
                                              CheckboxListTile(
                                                  contentPadding:
                                                      EdgeInsets.zero,
                                                  title: Text(
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
                                                    child: Text('沒有符合的圖片',
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
                                                          image: images[index]))
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
                                                    child: Text('沒有符合的單字',
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
                                                                        '${word.learnerMeaning ?? '中文意思待補齊'}\n${posLabel(word.pos)}'
                                                                        '${word.cefr == null ? '' : ' · ${levelLabel(word.cefr!)}'}'
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
            child: Text(label,
                style: MFont.manrope(14, FontWeight.w700,
                    selected ? MColors.primaryDeep : MColors.ink)),
          ),
        ),
      );
}

List<Map<String, dynamic>> databaseImageTags(Map<String, dynamic> image) => [
      for (final tag in (image['tags'] as List? ?? []))
        if ((tag as Map)['review_status'] == 'approved')
          Map<String, dynamic>.from(tag)
    ];

String databaseImageLabels(Map<String, dynamic> image, LexiconPack pack) =>
    databaseImageTags(image)
        .map((tag) {
          final word = pack.byId((tag['lexeme_id'] as num).toInt());
          if (word == null) return '單字待補齊';
          final sense =
              word.senses.where((s) => s.id == tag['sense_id']).firstOrNull;
          return '${word.lemma} · ${sense?.native ?? word.nativeMeaning ?? '中文意思待補齊'}';
        })
        .toSet()
        .join('、');

/// CEFR for a database tag: pack lexeme first, then tag metadata from the tagger.
String? databaseTagLevel(Map<String, dynamic> tag, LexiconPack pack) {
  final id = (tag['lexeme_id'] as num?)?.toInt();
  final word = id == null ? null : pack.byId(id);
  final raw = (tag['cefr'] as String?) ??
      (tag['modelLevel'] as String?) ??
      word?.cefr;
  if (raw == null) return null;
  final level = raw.toUpperCase();
  return cefrLevels.contains(level) ? level : null;
}

/// Approved tags grouped by CEFR (A1→C2), then unleveled.
List<MapEntry<String?, List<Map<String, dynamic>>>> groupedDatabaseImageTags(
    Map<String, dynamic> image, LexiconPack pack) {
  final byLevel = {
    for (final level in cefrLevels) level: <Map<String, dynamic>>[]
  };
  final unknown = <Map<String, dynamic>>[];
  for (final tag in databaseImageTags(image)) {
    final level = databaseTagLevel(tag, pack);
    if (level == null) {
      unknown.add(tag);
    } else {
      byLevel[level]!.add(tag);
    }
  }
  return [
    for (final level in cefrLevels)
      if (byLevel[level]!.isNotEmpty)
        MapEntry<String?, List<Map<String, dynamic>>>(level, byLevel[level]!),
    if (unknown.isNotEmpty)
      MapEntry<String?, List<Map<String, dynamic>>>(null, unknown),
  ];
}

/// A database picture as a photo the pinned view can show.
Photo databasePhoto(Map<String, dynamic> image) => Photo(
      id: 'db-${image['id']}',
      title: '',
      takenAt: DateTime(2000),
      createdAt: DateTime(2000),
      networkUrl: Uri.base.resolve(image['url'] as String).toString(),
      width: (image['width'] as num?)?.toInt(),
      height: (image['height'] as num?)?.toInt(),
    );

/// The vision model's labels on a database picture, as photo pins where it
/// saw them: words in the lexicon first, with their Chinese.
List<PinData> databasePins(Map<String, dynamic> image, LexiconPack pack,
    {int? max}) {
  final approvedIds = databaseImageTags(image)
      .map((tag) => (tag['lexeme_id'] as num?)?.toInt())
      .whereType<int>()
      .toSet();
  final labels = [
    for (final l in (image['labels'] as List? ?? []))
      if ((l as Map)['lexeme_id'] is num &&
          approvedIds.contains((l['lexeme_id'] as num).toInt()) &&
          (pack.byId((l['lexeme_id'] as num).toInt())?.full ?? false))
        Map<String, dynamic>.from(l)
  ];
  final pins = <PinData>[];
  for (final l in labels) {
    final point = [
      for (final v in (l['point'] as List? ?? [])) (v as num).toDouble()
    ];
    if (point.length < 2) continue;
    var x = point[0], y = point[1];
    final box = [
      for (final v in (l['box'] as List? ?? [])) (v as num).toDouble()
    ];
    if (box.length == 4 && x == 0.5 && y == 0.5) {
      // The model's "middle of the picture": the middle of its box instead.
      x = (box[0] + box[2]) / 2;
      y = (box[1] + box[3]) / 2;
    }
    final id = (l['lexeme_id'] as num?)?.toInt();
    final entry = id == null ? null : pack.byId(id);
    pins.add(PinData(
        id: '${l['word']}',
        anchor: LabelPoint(x, y),
        word: '${l['word']}',
        zh: entry?.nativeMeaning?.split('、').first ?? '',
        linked: entry != null));
    if (max != null && pins.length >= max) break;
  }
  return pins;
}

void openDatabaseWord(BuildContext context, int id) =>
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => DatabaseWordScreen(wordId: id)));

class DatabaseImageTile extends StatelessWidget {
  final Map<String, dynamic> image;
  const DatabaseImageTile({super.key, required this.image});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: MDecor.card(radius: MRadii.lg),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) =>
                  DatabaseImageScreen(imageId: (image['id'] as num).toInt()))),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(
                child: PinnedPhoto(
                    photo: databasePhoto(image),
                    pins: databasePins(image, LexiconPack.instance, max: 4),
                    radius: 0)),
            Padding(
                padding: const EdgeInsets.all(MSpace.xs),
                child: Text(_groupedTileLabels(image, LexiconPack.instance),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: MFont.inter(11, FontWeight.w500, MColors.muted))),
          ])),
    );
  }
}

class DatabaseImage extends StatelessWidget {
  final Map<String, dynamic> image;
  const DatabaseImage({super.key, required this.image});
  @override
  Widget build(BuildContext context) => Image.network(
        Uri.base.resolve(image['url'] as String).toString(),
        fit: BoxFit.contain,
        semanticLabel: databaseImageLabels(image, LexiconPack.instance),
        loadingBuilder: (_, child, progress) => progress == null
            ? child
            : const Center(
                child: CircularProgressIndicator(color: MColors.primary)),
        errorBuilder: (context, error, stack) =>
            Center(child: Text('圖片暫時無法載入', style: MFont.bodyMuted)),
      );
}

class DatabaseImageScreen extends StatelessWidget {
  final int imageId;
  const DatabaseImageScreen({super.key, required this.imageId});
  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: LexiconPack.instance,
      builder: (context, _) {
        final pack = LexiconPack.instance;
        final image =
            pack.catalogImages.where((i) => i['id'] == imageId).firstOrNull;
        return Scaffold(
            backgroundColor: MColors.canvas,
            appBar: AppBar(title: const Text('圖片與單字標籤')),
            body: image == null
                ? Center(child: Text('這張圖片已從資料庫移除', style: MFont.bodyMuted))
                : ListView(padding: const EdgeInsets.all(MSpace.md), children: [
                    Container(
                      decoration: MDecor.card(radius: MRadii.lg),
                      clipBehavior: Clip.antiAlias,
                      child: SizedBox(
                          height: 360,
                          child: PinnedPhoto(
                              photo: databasePhoto(image),
                              pins: databasePins(image, pack),
                              radius: 0,
                              onPinTap: (pin) {
                                final word = pack.lookup(pin.word);
                                if (word != null) {
                                  openDatabaseWord(context, word.entry.id);
                                }
                              })),
                    ),
                    const SizedBox(height: MSpace.md),
                    Text('圖片標籤', style: MFont.titleSm),
                    const SizedBox(height: 2),
                    Text('點標籤查看中文意思與例句。', style: MFont.caption),
                    const SizedBox(height: MSpace.sm),
                    ..._groupedTagSections(context, image, pack),
                    const SizedBox(height: MSpace.md),
                    Container(
                      padding: const EdgeInsets.all(MSpace.md),
                      decoration: MDecor.softCard(color: MColors.surfaceSoft),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                              '圖片來源：${image['source'] == 'wikimedia_commons' ? '維基共享資源' : image['source']}',
                              style: MFont.caption),
                          if (image['author'] != null) ...[
                            const SizedBox(height: 4),
                            Text('作者：${image['author']}', style: MFont.caption),
                          ],
                          if (image['license'] != null) ...[
                            const SizedBox(height: 4),
                            Text('授權：${image['license']}',
                                style: MFont.caption),
                          ],
                          if (image['attribution'] != null) ...[
                            const SizedBox(height: 4),
                            Text('${image['attribution']}',
                                style: MFont.caption),
                          ],
                        ],
                      ),
                    ),
                  ]));
      });
}

class DatabaseWordScreen extends StatelessWidget {
  final int wordId;
  const DatabaseWordScreen({super.key, required this.wordId});
  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: LexiconPack.instance,
      builder: (context, _) {
        final pack = LexiconPack.instance;
        final word = pack.byId(wordId);
        if (word == null) {
          return Scaffold(
              backgroundColor: MColors.canvas,
              appBar: AppBar(title: const Text('單字詳情')),
              body: Center(child: Text('這個單字已從資料庫移除', style: MFont.bodyMuted)));
        }
        final scope = AppScope.of(context);
        final example = word.examples
            .where((e) => (e.translation ?? '').isNotEmpty)
            .firstOrNull;
        final images = pack.catalogImages
            .where((image) => databaseImageTags(image)
                .any((tag) => tag['lexeme_id'] == wordId))
            .toList();
        return Scaffold(
            backgroundColor: MColors.canvas,
            appBar: AppBar(title: const Text('單字詳情')),
            body: ListView(padding: const EdgeInsets.all(MSpace.md), children: [
              Text(word.lemma,
                  style: MFont.manrope(28, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 4),
              Row(
                children: [
                  // Flexible: 「動詞 · B2 進階 · 罕見用法」 + badge is wider
                  // than a phone (390 px); the label wraps instead.
                  Flexible(
                    child: Text(
                        '${posLabel(word.pos)}${word.cefr == null ? '' : ' · ${levelLabel(word.cefr!)}'}'
                        '${word.rareUsage ? ' · 罕見用法' : ''}',
                        style: MFont.bodyMuted),
                  ),
                  if (word.cefr != null) ...[
                    const SizedBox(width: 8),
                    LevelBadge(word.cefr!),
                  ],
                ],
              ),
              if (word.ipa != null) ...[
                const SizedBox(height: 2),
                Text(word.ipa!, style: MFont.caption),
              ],
              const SizedBox(height: MSpace.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: Tap(
                  onTap: () => scope.speaker.say(word.lemma,
                      language: pack.target ?? 'en',
                      audioUrl: word.audio == null || pack.mediaBase == null
                          ? null
                          : Uri.base.resolve(pack.mediaBase!).replace(
                              queryParameters: {
                                  'path': word.audio!
                                }).toString()),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: MSpace.sm, vertical: 6),
                    decoration: MDecor.chipSurface(active: true),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.volume_up_outlined,
                            size: 16, color: MColors.primary),
                        const SizedBox(width: 6),
                        Text('聽發音',
                            style: MFont.manrope(
                                13, FontWeight.w700, MColors.primaryDeep)),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: MSpace.md),
              Text(word.learnerMeaning ?? '中文意思待補齊',
                  style: MFont.manrope(20, FontWeight.w800, MColors.primary)),
              if (word.senses.length > 1) ...[
                const SizedBox(height: MSpace.sm),
                Container(
                  decoration: MDecor.softCard(color: MColors.surfaceSoft),
                  clipBehavior: Clip.antiAlias,
                  // The tile's ink and background paint on this Material,
                  // above the card's color (otherwise they are invisible).
                  child: Material(
                    type: MaterialType.transparency,
                    child: ExpansionTile(
                        title: Text('更多意思',
                            style: MFont.manrope(
                                14, FontWeight.w700, MColors.ink)),
                        children: [
                          for (final sense in word.senses)
                            if (sense.native != null)
                              Padding(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: MSpace.md, vertical: MSpace.xs),
                                child: Align(
                                  alignment: Alignment.centerLeft,
                                  child: Text(sense.native!,
                                      style: MFont.manrope(
                                          14, FontWeight.w600, MColors.ink)),
                                ),
                              )
                        ]),
                  ),
                ),
              ],
              if (example != null) ...[
                const SizedBox(height: MSpace.md),
                Container(
                  padding: const EdgeInsets.all(MSpace.md),
                  decoration: MDecor.softCard(color: MColors.surfaceSoft),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('實用例句',
                          style:
                              MFont.manrope(14, FontWeight.w700, MColors.ink)),
                      const SizedBox(height: MSpace.xs),
                      Text(example.text,
                          style:
                              MFont.manrope(15, FontWeight.w700, MColors.ink)),
                      const SizedBox(height: 4),
                      Text(example.translation!, style: MFont.bodyMuted),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: MSpace.lg),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                    onPressed: () {
                      final repo = scope.repository;
                      final messenger = ScaffoldMessenger.of(context)
                        ..removeCurrentSnackBar();
                      try {
                        final added = repo.addWord(
                            word: word.lemma,
                            pos: shortPos(word.pos),
                            meaning: word.learnerMeaning ?? '',
                            level: word.cefr);
                        repo.linkLexicon(pack);
                        // No Chinese yet: the card waits (問題回報 #44, #100).
                        final waiting = (repo.entry(added.id)?.meaning ?? '')
                            .trim()
                            .isEmpty;
                        messenger.showSnackBar(SnackBar(
                            content: Text(waiting
                                ? '已加入我的收藏；中文意思補齊後會自動排進複習'
                                : '已加入我的收藏與複習字卡')));
                      } on DuplicateWordException {
                        // Swiped away as 已學會 earlier: adding it again means
                        // studying it again (問題回報 #99).
                        final e = repo.entryByWord(word.lemma);
                        final archived = e != null && repo.isArchived(e.id);
                        if (archived) repo.restoreWord(e.word);
                        messenger.showSnackBar(SnackBar(
                            content:
                                Text(archived ? '已從「已學會」放回複習' : '這個單字已在我的收藏')));
                      }
                    },
                    child: const Text('加入我的收藏與複習')),
              ),
              const SizedBox(height: MSpace.lg),
              Text('資料庫圖片（${images.length}）', style: MFont.titleSm),
              const SizedBox(height: MSpace.xs),
              if (images.isEmpty)
                Container(
                  padding: const EdgeInsets.all(MSpace.lg),
                  decoration: MDecor.emptyStateCard(),
                  child: Text('資料庫尚未加入這個單字的圖片', style: MFont.bodyMuted),
                ),
              for (final image in images)
                Padding(
                    padding: const EdgeInsets.only(top: MSpace.sm),
                    child: SizedBox(
                        height: 240, child: DatabaseImageTile(image: image))),
            ]));
      });
}


String _groupedTileLabels(Map<String, dynamic> image, LexiconPack pack) {
  final groups = groupedDatabaseImageTags(image, pack);
  if (groups.isEmpty) return databaseImageLabels(image, pack);
  return groups.map((group) {
    final words = <String>[];
    for (final tag in group.value) {
      words.add(databaseImageLabels({'tags': [tag]}, pack));
    }
    final head = group.key == null ? '\u672a\u5206\u7d1a' : levelLabel(group.key!);
    return '$head\uff1a${words.join('\u3001')}';
  }).join(' \u00b7 ');
}

List<Widget> _groupedTagSections(
    BuildContext context, Map<String, dynamic> image, LexiconPack pack) {
  final groups = groupedDatabaseImageTags(image, pack);
  if (groups.isEmpty) {
    return [
      Container(
        padding: const EdgeInsets.all(MSpace.lg),
        decoration: MDecor.emptyStateCard(),
        child: Text('\u9019\u5f35\u5716\u7247\u5c1a\u7121\u5df2\u78ba\u8a8d\u6a19\u7c64',
            style: MFont.bodyMuted),
      ),
    ];
  }
  final out = <Widget>[];
  for (final group in groups) {
    out.add(Padding(
      padding: const EdgeInsets.only(top: MSpace.sm, bottom: MSpace.xs),
      child: Row(children: [
        if (group.key != null) ...[
          LevelBadge(group.key!),
          const SizedBox(width: MSpace.xs),
        ],
        Flexible(
          child: Text(
            group.key == null ? '\u672a\u5206\u7d1a' : levelLabel(group.key!),
            style: MFont.manrope(14, FontWeight.w700, MColors.ink),
          ),
        ),
      ]),
    ));
    for (final tag in group.value) {
      final word = pack.byId((tag['lexeme_id'] as num).toInt());
      final label = databaseImageLabels({'tags': [tag]}, pack);
      out.add(Container(
        margin: const EdgeInsets.only(bottom: MSpace.xxs),
        decoration: MDecor.listTileSurface(showDivider: true),
        child: InkWell(
          onTap: word == null ? null : () => openDatabaseWord(context, word.id),
          borderRadius: BorderRadius.circular(MRadii.sm),
          child: Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: MSpace.sm, vertical: MSpace.xs),
            child: Row(children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style:
                            MFont.manrope(15, FontWeight.w700, MColors.ink)),
                    const SizedBox(height: 2),
                    Text(
                        switch (tag['review_status']) {
                          'approved' => '\u5df2\u78ba\u8a8d',
                          'rejected' => '\u5df2\u6392\u9664\u7684\u914d\u5c0d',
                          _ => '\u5716\u7247\u8207\u55ae\u5b57\u7684\u914d\u5c0d\u5f85\u78ba\u8a8d'
                        },
                        style: MFont.caption),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: MColors.muted, size: 18),
            ]),
          ),
        ),
      ));
    }
  }
  return out;
}

