part of '../screens/database_library_screen.dart';

/// 「搜尋的字 cluster 在 中階（B1）」 with a switch to that level, for a picture
/// found by a word the chosen level hides (問題回報 #302 decision: keep the
/// cross-level search, name the hit and its level, offer the switch).
///
/// The album shows it once under the search box when every result has the
/// same hit (問題回報 #397), on each tile only when the results are mixed.
class DatabaseSearchHint extends StatelessWidget {
  final ({String word, String? level}) hit;
  final ValueChanged<String?> onSwitch;
  final bool compact;
  const DatabaseSearchHint(
      {super.key,
      required this.hit,
      required this.onSwitch,
      this.compact = false});

  @override
  Widget build(BuildContext context) {
    final target = ui(context, hit.level ?? '全部');
    final where = hit.level == null ? '沒有分級' : '在 ${levelLabel(hit.level!)}';
    final spoken = hit.level == null
        ? '搜尋的字 ${hit.word} 沒有分級，切到 $target'
        : '搜尋的字 ${hit.word} 在 ${ui(context, levelLabel(hit.level!))}，切到 $target';
    return Semantics(
      button: true,
      label: ui(context, spoken),
      excludeSemantics: true,
      child: Tap(
        onTap: () => onSwitch(hit.level),
        child: Container(
          padding: EdgeInsets.symmetric(
              horizontal: compact ? MSpace.xs : MSpace.md,
              vertical: compact ? 4 : MSpace.sm),
          color: MColors.surfaceSoft,
          child: Row(children: [
            Expanded(
              child: UiText('搜尋的字 ${hit.word} $where',
                  maxLines: compact ? 2 : null,
                  overflow: compact ? TextOverflow.ellipsis : null,
                  style: compact ? MFont.caption : MFont.bodyMuted),
            ),
            const SizedBox(width: 4),
            UiText('切到 $target',
                style: MFont.inter(
                    compact ? 11 : 13, FontWeight.w700, MColors.primaryDeep)),
          ]),
        ),
      ),
    );
  }
}

class DatabaseImageTile extends StatelessWidget {
  final Map<String, dynamic> image;

  /// Only this CEFR level's labels; null shows every level.
  final String? level;

  /// The album's search text, to explain a hit at another level.
  final String search;

  /// Switches the album's level (the hint's 「切到 B1」).
  final ValueChanged<String?>? onLevelChanged;

  /// Whether this tile explains its own cross-level hit. The album turns it
  /// off when every result shares one hint, which it then shows once under
  /// the search box instead of on each picture (問題回報 #397).
  final bool showSearchHint;

  /// 卡 #1415: a fixed picture height with the tags below it, so the tile
  /// grows instead of squeezing the picture under its labels (null = the
  /// album's grid cell, where the picture takes what the tags leave).
  final double? photoHeight;

  /// Owner 11/26: on 單字詳情 the whole picture and every tag show.
  final bool expanded;
  const DatabaseImageTile(
      {super.key,
      this.photoHeight,
      this.expanded = false,
      required this.image,
      this.level,
      this.search = '',
      this.onLevelChanged,
      this.showSearchHint = true});
  @override
  Widget build(BuildContext context) {
    final elsewhere = showSearchHint
        ? databaseSearchElsewhere(image, LexiconPack.instance, search, level)
        : null;
    return Container(
      decoration: MDecor.card(radius: MRadii.lg),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => DatabaseImageScreen(
                  imageId: (image['id'] as num).toInt(),
                  initialLevel: level,
                  search: search))),
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize:
                  photoHeight == null ? MainAxisSize.max : MainAxisSize.min,
              children: [
            () {
              final photo = PinnedPhoto(
                  photo: databasePhoto(image),
                  pins: databasePins(image, LexiconPack.instance,
                      max: 4, level: level),
                  // Owner 11/26: the whole picture, never cropped to a strip.
                  fit: expanded ? BoxFit.contain : BoxFit.cover,
                  radius: 0);
              return photoHeight == null
                  ? Expanded(child: photo)
                  : SizedBox(height: photoHeight, child: photo);
            }(),
            if (elsewhere != null && onLevelChanged != null)
              DatabaseSearchHint(
                  hit: elsewhere, onSwitch: onLevelChanged!, compact: true),
            ConstrainedBox(
              constraints: BoxConstraints(
                  maxHeight: expanded ? double.infinity : 100),
              child: SingleChildScrollView(
                child: Padding(
                  padding: const EdgeInsets.all(MSpace.xs),
                  child: DatabaseTagSections(
                      image: image,
                      pack: LexiconPack.instance,
                      level: level,
                      compact: true,
                      expanded: expanded),
                ),
              ),
            ),
          ])),
    );
  }
}

/// Owner 11/26: the picture's own shape at [width], at most [max] tall, so a
/// wide screen shows the whole photo instead of a 160 pt strip.
double databasePhotoHeight(Map<String, dynamic> image, double width,
    {double max = 600}) {
  final w = (image['width'] as num?)?.toDouble();
  final h = (image['height'] as num?)?.toDouble();
  final aspect = (w != null && h != null && w > 0 && h > 0) ? w / h : 4 / 3;
  return (width / aspect).clamp(120.0, max);
}

class DatabaseImage extends StatelessWidget {
  final Map<String, dynamic> image;
  const DatabaseImage({super.key, required this.image});
  @override
  Widget build(BuildContext context) {
    final resolved = resolvePackMedia(image['url'] as String);
    final label = databaseImageLabels(image, LexiconPack.instance,
        tr: (s) => ui(context, s));
    final missing = Center(child: UiText('圖片暫時無法載入', style: MFont.bodyMuted));
    if (packMediaIsAsset(resolved)) {
      return Image.asset(
        resolved,
        fit: BoxFit.contain,
        semanticLabel: label,
        errorBuilder: (context, error, stack) => missing,
      );
    }
    // 問題回報 #859: from the disk cache, at the size the review asks for.
    return Image(
      image: networkPhoto(sizedServerImage(resolved)),
      fit: BoxFit.contain,
      semanticLabel: label,
      loadingBuilder: (_, child, progress) => progress == null
          ? child
          : const Center(
              child: CircularProgressIndicator(color: MColors.primary)),
      errorBuilder: (context, error, stack) => missing,
    );
  }
}

/// Learner-facing credit lines. Raw source codes stay off the page;
/// Wikimedia Commons is the only source named in plain language.
/// Numeric-only ids are dropped. Attribution stays available for CC BY-SA.
List<Widget> _imageInfoLines(Map<String, dynamic> image) {
  String? visible(dynamic raw) {
    if (raw is! String) return null;
    final text = raw.trim();
    if (text.isEmpty || RegExp(r'^#?\d+$').hasMatch(text)) return null;
    return text;
  }

  final lines = <Widget>[];
  void add(Widget child) {
    if (lines.isNotEmpty) lines.add(const SizedBox(height: 4));
    lines.add(child);
  }

  if (image['source'] == 'wikimedia_commons') {
    add(UiText('圖片來源：維基共享資源', style: MFont.caption));
  }
  final author = visible(image['author']);
  if (author != null) add(UiText('作者：$author', style: MFont.caption));
  final license = visible(image['license']);
  if (license != null) add(UiText('授權：$license', style: MFont.caption));
  final licenseUrl = visible(image['license_url']) ?? licenseUrlFor(license);
  if (licenseUrl != null) {
    add(Builder(
        builder: (context) => SelectableText(ui(context, '授權條文：$licenseUrl'),
            style: MFont.caption)));
  }
  final attribution = visible(image['attribution']);
  if (attribution != null) add(Text(attribution, style: MFont.caption));
  final pageUrl = visible(image['page_url']);
  if (pageUrl != null) {
    add(Builder(
        builder: (context) =>
            SelectableText(ui(context, '來源頁：$pageUrl'), style: MFont.caption)));
  }
  return lines;
}

class _DatabaseImageInfo extends StatelessWidget {
  final List<Widget> lines;
  const _DatabaseImageInfo({required this.lines});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: MDecor.softCard(color: MColors.surfaceSoft),
      clipBehavior: Clip.antiAlias,
      child: Material(
        type: MaterialType.transparency,
        child: ExpansionTile(
          key: const ValueKey('image-info'),
          initiallyExpanded: false,
          tilePadding: const EdgeInsets.symmetric(horizontal: MSpace.md),
          childrenPadding:
              const EdgeInsets.fromLTRB(MSpace.md, 0, MSpace.md, MSpace.md),
          title: UiText('圖片資訊',
              style: MFont.manrope(14, FontWeight.w700, MColors.ink)),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: lines,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DatabaseImageScreen extends StatefulWidget {
  final int imageId;

  /// The level the album was showing when the picture was opened.
  final String? initialLevel;

  /// The album's search text, to explain a hit at another level.
  final String search;
  const DatabaseImageScreen(
      {super.key, required this.imageId, this.initialLevel, this.search = ''});
  @override
  State<DatabaseImageScreen> createState() => _DatabaseImageScreenState();
}

class _DatabaseImageScreenState extends State<DatabaseImageScreen> {
  late String? _level = widget.initialLevel;

  int get imageId => widget.imageId;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: LexiconPack.instance,
      builder: (context, _) {
        final pack = LexiconPack.instance;
        final image =
            pack.catalogImages.where((i) => i['id'] == imageId).firstOrNull;
        final info = image == null ? const <Widget>[] : _imageInfoLines(image);
        final elsewhere = image == null
            ? null
            : databaseSearchElsewhere(image, pack, widget.search, _level);
        return Scaffold(
            backgroundColor: MColors.canvas,
            appBar: AppBar(title: const UiText('圖片與單字標籤')),
            body: image == null
                ? Center(child: UiText('這張圖片已從資料庫移除', style: MFont.bodyMuted))
                : ListView(padding: const EdgeInsets.all(MSpace.md), children: [
                    Container(
                      decoration: MDecor.card(radius: MRadii.lg),
                      clipBehavior: Clip.antiAlias,
                      child: SizedBox(
                          height: 360,
                          child: PinnedPhoto(
                              photo: databasePhoto(image),
                              pins: databasePins(image, pack, level: _level),
                              radius: 0,
                              onPinTap: (pin) {
                                final id = pin.lexemeId ??
                                    pack.lookup(pin.word)?.entry.id;
                                if (id != null) openDatabaseWord(context, id);
                              })),
                    ),
                    const SizedBox(height: MSpace.sm),
                    LabelLevelBar(
                        level: _level,
                        defaultLabel: '全部',
                        onChanged: (l) => setState(() => _level = l)),
                    if (elsewhere != null) ...[
                      const SizedBox(height: MSpace.sm),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(MRadii.md),
                        child: DatabaseSearchHint(
                            hit: elsewhere,
                            onSwitch: (l) => setState(() => _level = l)),
                      ),
                    ],
                    const SizedBox(height: MSpace.md),
                    UiText('圖片標籤', style: MFont.titleSm),
                    const SizedBox(height: 2),
                    UiText('點標籤查看{N}意思與例句。', style: MFont.caption),
                    const SizedBox(height: MSpace.sm),
                    DatabaseTagSections(
                        image: image, pack: pack, level: _level),
                    if (info.isNotEmpty) ...[
                      const SizedBox(height: MSpace.md),
                      _DatabaseImageInfo(lines: info),
                    ],
                  ]));
      });
}
