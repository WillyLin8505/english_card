import '../l10n/ui_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../services/photo_store.dart';
import '../widgets/mobile/photo_widgets.dart';

/// 項目照片 — Figma "Project Photos · Mobile" (39:65): a searchable grid
/// of photo cards. Three sources use it:
/// - a word: every photo it appears in (spec: 同一單字可連結多張照片),
///   its chip highlighted on each card, as in the mock;
/// - an album: the album's photos;
/// - search: every photo.
class PhotoGridScreen extends StatefulWidget {
  final String? wordEntryId;
  final String? albumId;

  const PhotoGridScreen.word({super.key, required String this.wordEntryId})
      : albumId = null;
  const PhotoGridScreen.album({super.key, required String this.albumId})
      : wordEntryId = null;
  const PhotoGridScreen.search({super.key})
      : wordEntryId = null,
        albumId = null;

  @override
  State<PhotoGridScreen> createState() => _PhotoGridScreenState();
}

class _PhotoGridScreenState extends State<PhotoGridScreen> {
  final _query = TextEditingController();

  /// The 標籤程度 picker; null shows the words being learned.
  String? _level;

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final wordId = widget.wordEntryId;
        final albumId = widget.albumId;
        final title = wordId != null
            ? '項目照片'
            : albumId != null
                ? (repo.album(albumId)?.name ?? '相片冊')
                : '搜尋照片';
        final all = wordId != null
            // The word's photos skip ones whose original file is gone
            // (問題回報 #283); an album still lists them so they can be
            // deleted, drawn as their placeholder.
            ? [
                for (final p in repo.photosOfWord(wordId))
                  if (!PhotoStore.lostOriginal(p)) p
              ]
            : albumId != null
                ? repo.photosInAlbum(albumId)
                : repo.photos;

        // 相片冊縮圖不顯示已學會標籤.
        List<WordEntry> wordsOf(Photo p) {
          final words = [for (final l in repo.visibleLabels(p.id)) l.entry];
          // The focus word first, then the rest.
          words.sort((a, b) =>
              (a.id == wordId ? 0 : 1).compareTo(b.id == wordId ? 0 : 1));
          return {for (final w in words) w.id: w}.values.toList();
        }

        // A chosen level shows the photo's candidate pool at that level
        // (問題回報 #113) — read-only: the saved words and the photo's dial
        // setting are left as they are. Learned words stay hidden here too.
        final focusWord = wordId == null ? null : repo.entry(wordId)?.word;
        List<(String, bool)> labelsOf(Photo p) {
          final level = _level;
          if (level == null) {
            return [for (final w in wordsOf(p)) (w.word, w.id == wordId)];
          }
          final seen = <String>{};
          final labels = <(String, bool)>[];
          for (final c in p.candidates) {
            final learned = repo.entryByWord(c.word);
            if (c.level != level ||
                !seen.add(c.word) ||
                (learned != null && repo.isArchived(learned.id))) {
              continue;
            }
            labels.add((c.word, c.word == focusWord));
          }
          return [
            ...labels.where((l) => l.$2),
            ...labels.where((l) => !l.$2),
          ];
        }

        final q = _query.text.trim().toLowerCase();
        final photos = [
          for (final p in all)
            if (q.isEmpty ||
                p.title.toLowerCase().contains(q) ||
                (p.place ?? '').toLowerCase().contains(q) ||
                repo
                    .activeLabels(p.id)
                    .map((l) => l.entry)
                    .any((w) => w.word.contains(q) || w.meaning.contains(q)))
              p,
        ];

        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                MNavBar(
                  title: title,
                  leading: const BackNavButton(),
                  trailing: ShareNavButton(
                    onTap: () => SharePlus.instance.share(ShareParams(
                      title: title,
                      text: '$title（${photos.length} 張）\n'
                          '${photos.map((p) => '${p.title}：${labelsOf(p).map((l) => l.$1).join(', ')}').join('\n')}',
                    )),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                  child: _SearchBar(
                      controller: _query, onChanged: (_) => setState(() {})),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 0, 0),
                  child: LabelLevelBar(
                    level: _level,
                    defaultLabel: '學習中',
                    onChanged: (l) => setState(() => _level = l),
                  ),
                ),
                Expanded(
                  child: photos.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(32),
                            child: UiText(
                              all.isEmpty ? '還沒有照片' : '找不到符合的照片',
                              style: MFont.inter(
                                  14, FontWeight.w500, MColors.gray500),
                            ),
                          ),
                        )
                      : GridView.builder(
                          padding: const EdgeInsets.all(16),
                          gridDelegate:
                              const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 2,
                            mainAxisSpacing: 16,
                            crossAxisSpacing: 12,
                            mainAxisExtent: 246,
                          ),
                          itemCount: photos.length,
                          itemBuilder: (context, i) => _PhotoCard(
                            photo: photos[i],
                            labels: labelsOf(photos[i]),
                            emptyText:
                                _level == null ? null : '沒有 $_level 標籤',
                            onTap: () =>
                                scope.navigator.openPhoto(photos[i].id),
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
}

/// Figma search-bar (54:333): SDS search icon on the left, 16px radius.
class _SearchBar extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  const _SearchBar({required this.controller, required this.onChanged});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: MColors.surface,
          border: Border.all(color: MColors.hairline),
          borderRadius: MRadii.rLg,
          boxShadow: MShadows.soft,
        ),
        child: Row(
          children: [
            SvgPicture.asset('assets/figma/search.svg', width: 16, height: 16),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: controller,
                onChanged: onChanged,
                style: MFont.manrope(16, FontWeight.w500, MColors.gray900),
                decoration: InputDecoration(
                  isCollapsed: true,
                  contentPadding: EdgeInsets.zero,
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  hintText: ui(context, '搜尋照片'),
                  hintStyle:
                      MFont.manrope(16, FontWeight.w500, MColors.gray500),
                ),
              ),
            ),
          ],
        ),
      );
}

/// Figma "Photo Card / 晨光陽台" (54:339).
class _PhotoCard extends StatelessWidget {
  final Photo photo;

  /// Each label and whether it is the focus word (highlighted).
  final List<(String, bool)> labels;

  /// Shown instead of the chips when [labels] is empty.
  final String? emptyText;
  final VoidCallback onTap;

  const _PhotoCard({
    required this.photo,
    required this.labels,
    required this.emptyText,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final t = photo.takenAt;
    String two(int n) => n.toString().padLeft(2, '0');
    final date = '${t.year}/${two(t.month)}/${two(t.day)}';
    return Tap(
      onTap: onTap,
      label: photo.title,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 14),
        decoration: MDecor.card(radius: MRadii.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 130,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(MRadii.sm - 2),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    PhotoImage(photo),
                    if (photo.awaitingTagging)
                      const Positioned(
                          top: 6, right: 6, child: HourglassBadge()),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            // Figma "Photo Info": a fixed 78px block; tags clipped to one row.
            SizedBox(
              height: 78,
              child: ClipRect(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(photo.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: MFont.inter(14, FontWeight.w600, MColors.gray900,
                            height: 1.4)),
                    const SizedBox(height: 4),
                    Text(
                        [if (photo.place != null) photo.place!, date]
                            .join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: MFont.inter(11, FontWeight.w400, MColors.gray500,
                            height: 1.4)),
                    const SizedBox(height: 4),
                    SizedBox(
                      height: 26,
                      child: labels.isEmpty && emptyText != null
                          ? Align(
                              alignment: Alignment.centerLeft,
                              child: Text(emptyText!,
                                  style: MFont.inter(
                                      11, FontWeight.w500, MColors.gray500)),
                            )
                          : Wrap(
                              spacing: 6,
                              clipBehavior: Clip.hardEdge,
                              children: [
                                for (final (label, focus) in labels)
                                  FilterPill(label: label, active: focus),
                              ],
                            ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
