part of '../screens/database_library_screen.dart';

/// Each image/level owns its expansion state; filtering cannot transfer it
/// to a different level or picture.
class DatabaseTagSections extends StatelessWidget {
  final Map<String, dynamic> image;
  final LexiconPack pack;
  final String? level;
  final bool compact;
  const DatabaseTagSections(
      {super.key,
      required this.image,
      required this.pack,
      this.level,
      this.compact = false});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: _sections(context),
      );

  List<Widget> _sections(BuildContext context) {
    final groups = groupedDatabaseImageTags(image, pack)
        .where((g) => level == null || g.key == level)
        .toList();
    if (groups.isEmpty) {
      return [
        Container(
          padding: const EdgeInsets.all(MSpace.lg),
          decoration: MDecor.emptyStateCard(),
          child: Text(
              level == null
                  ? '\u9019\u5f35\u5716\u7247\u5c1a\u7121\u5df2\u78ba\u8a8d\u6a19\u7c64'
                  : '\u9019\u5f35\u5716\u7247\u6c92\u6709 ${levelLabel(level!)} \u7684\u6a19\u7c64\uff0c\u63db\u500b\u7a0b\u5ea6\u770b\u770b\u3002',
              style: MFont.bodyMuted),
        ),
      ];
    }
    // Card #510 (問題回報 #524): a label with no point draws no pin; the
    // list says so ("整張圖") instead of looking like a missing pin.
    final positioned = <int>{
      for (final l in (image['labels'] as List? ?? []))
        if (l is Map &&
            l['lexeme_id'] is num &&
            (l['point'] as List? ?? []).length >= 2)
          (l['lexeme_id'] as num).toInt()
    };
    return [
      for (final group in groups)
        _DatabaseTagGroup(
            key: ValueKey('${image['id']}:${group.key}'),
            group: group,
            pack: pack,
            positioned: positioned,
            compact: compact)
    ];
  }
}

class _DatabaseTagGroup extends StatefulWidget {
  final MapEntry<String?, List<Map<String, dynamic>>> group;
  final LexiconPack pack;
  final Set<int> positioned;
  final bool compact;
  const _DatabaseTagGroup(
      {super.key,
      required this.group,
      required this.pack,
      this.positioned = const {},
      required this.compact});
  @override
  State<_DatabaseTagGroup> createState() => _DatabaseTagGroupState();
}

class _DatabaseTagGroupState extends State<_DatabaseTagGroup> {
  bool _expanded = false;
  @override
  Widget build(BuildContext context) {
    final group = widget.group;
    final pack = widget.pack;
    final visibleTags = _expanded ? group.value : group.value.take(3);
    final out = <Widget>[];
    if (widget.compact) {
      out.add(Text(_compactTagLabels(group, pack, visibleTags),
          style: MFont.inter(11, FontWeight.w500, MColors.muted)));
    } else {
      out.add(Padding(
        padding: const EdgeInsets.only(top: MSpace.sm, bottom: MSpace.xs),
        child: Row(children: [
          if (group.key != null) ...[
            LevelBadge(group.key!),
            const SizedBox(width: MSpace.xs),
          ],
          Flexible(
            // UI copy: an English speaker reads "Beginner (A1)" (\u5361 #496).
            child: UiText(
              group.key == null ? '\u672a\u5206\u7d1a' : levelLabel(group.key!),
              style: MFont.manrope(14, FontWeight.w700, MColors.ink),
            ),
          ),
        ]),
      ));
      for (final tag in visibleTags) {
        final word = pack.byId((tag['lexeme_id'] as num).toInt());
        final label = databaseImageLabels({
          'tags': [tag]
        }, pack);
        final wholePicture =
            !widget.positioned.contains((tag['lexeme_id'] as num).toInt());
        out.add(Container(
          margin: const EdgeInsets.only(bottom: MSpace.xxs),
          decoration: MDecor.listTileSurface(showDivider: true),
          child: InkWell(
            onTap:
                word == null ? null : () => openDatabaseWord(context, word.id),
            borderRadius: BorderRadius.circular(MRadii.sm),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: MSpace.sm, vertical: MSpace.xs),
              child: Row(children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Flexible(
                          child: Text(label,
                              style: MFont.manrope(
                                  15, FontWeight.w700, MColors.ink)),
                        ),
                        if (wholePicture) ...[
                          const SizedBox(width: MSpace.xs),
                          // #510: no pin on the photo; the word is about
                          // the whole picture, not a missing pin.
                          Container(
                            key: ValueKey(
                                'whole-picture-${tag['lexeme_id']}'),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 1),
                            decoration: BoxDecoration(
                                color: MColors.surfaceSoft,
                                borderRadius:
                                    BorderRadius.circular(MRadii.sm)),
                            child: UiText('整張圖', style: MFont.caption),
                          ),
                        ],
                      ]),
                      if (group.key != null && databaseTagEstimated(tag, pack)) ...[
                        const SizedBox(height: 2),
                        // UI copy, localized for native=en/fr (\u5361 #496).
                        UiText('\u7b49\u7d1a\u70ba\u8a5e\u983b\u4f30\u7b97',
                            style: MFont.caption),
                      ],
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
    if (group.value.length > 3) {
      out.add(Align(
          alignment: Alignment.centerLeft,
          child: TextButton(
            key: ValueKey('toggle-${group.key ?? 'unknown'}'),
            onPressed: () => setState(() => _expanded = !_expanded),
            child: UiText(_expanded ? '收合' : '展開全部（${group.value.length}）'),
          )));
    }
    return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch, children: out);
  }
}

String _compactTagLabels(MapEntry<String?, List<Map<String, dynamic>>> group,
    LexiconPack pack, Iterable<Map<String, dynamic>> tags) {
  final words = [
    for (final tag in tags)
      '${databaseImageLabels({
            'tags': [tag]
          }, pack)}${group.key != null && databaseTagEstimated(tag, pack) ? '（估算）' : ''}'
  ];
  final head = group.key == null ? '未分級' : levelLabel(group.key!);
  return '$head：${words.join('、')}';
}
