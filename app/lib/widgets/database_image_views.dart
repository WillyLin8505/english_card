part of '../screens/database_library_screen.dart';

class DatabaseImageTile extends StatelessWidget {
  final Map<String, dynamic> image;

  /// Only this CEFR level's labels; null shows every level.
  final String? level;
  const DatabaseImageTile({super.key, required this.image, this.level});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: MDecor.card(radius: MRadii.lg),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => DatabaseImageScreen(
                  imageId: (image['id'] as num).toInt(), initialLevel: level))),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(
                child: PinnedPhoto(
                    photo: databasePhoto(image),
                    pins: databasePins(image, LexiconPack.instance,
                        max: 4, level: level),
                    radius: 0)),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 100),
              child: SingleChildScrollView(
                child: Padding(
                  padding: const EdgeInsets.all(MSpace.xs),
                  child: DatabaseTagSections(
                      image: image,
                      pack: LexiconPack.instance,
                      level: level,
                      compact: true),
                ),
              ),
            ),
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
            Center(child: UiText('圖片暫時無法載入', style: MFont.bodyMuted)),
      );
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
  final attribution = visible(image['attribution']);
  if (attribution != null) add(Text(attribution, style: MFont.caption));
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
  const DatabaseImageScreen(
      {super.key, required this.imageId, this.initialLevel});
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
                                final word = pack.lookup(pin.word);
                                if (word != null) {
                                  openDatabaseWord(context, word.entry.id);
                                }
                              })),
                    ),
                    const SizedBox(height: MSpace.sm),
                    LabelLevelBar(
                        level: _level,
                        defaultLabel: '全部',
                        onChanged: (l) => setState(() => _level = l)),
                    const SizedBox(height: MSpace.md),
                    UiText('圖片標籤', style: MFont.titleSm),
                    const SizedBox(height: 2),
                    UiText('點標籤查看中文意思與例句。', style: MFont.caption),
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
