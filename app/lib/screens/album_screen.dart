import '../l10n/ui_text.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'deck_browser_screen.dart';
import 'photo_grid_screen.dart';
import 'photo_picker_screen.dart';

/// 我的相片冊 — Figma photo-album-page (17:5), the 相片冊 tab: albums by
/// category, and 選擇新照片.
class AlbumScreen extends StatefulWidget {
  /// Overrides the top-bar 返回 action. Set when this screen is embedded
  /// (e.g. inside DatabaseLibraryScreen's 我的相片冊 toggle) so 返回 steps
  /// back to the embedding context instead of leaving the tab (問題回報
  /// #258).
  final VoidCallback? onBack;

  const AlbumScreen({super.key, this.onBack});

  @override
  State<AlbumScreen> createState() => _AlbumScreenState();
}

class _AlbumScreenState extends State<AlbumScreen> {
  String? _category;

  void _openAlbum(Album album) =>
      Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => PhotoGridScreen.album(albumId: album.id),
      ));

  void _search() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => const PhotoGridScreen.search(),
      ));

  Future<void> _rename(Album album) async {
    final repo = AppScope.of(context).repository;
    final controller = TextEditingController(text: album.name);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const UiText('重新命名相簿'),
        content: TextField(controller: controller, autofocus: true),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const UiText('取消')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, controller.text),
              child: const UiText('儲存')),
        ],
      ),
    );
    if (name != null) repo.renameAlbum(album.id, name);
  }

  /// 卡片集 (別人的相片冊) download entry (問題回報 #440): lives here, and a
  /// downloaded deck comes back as one tile in the grid below.
  void _downloadAlbums() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => const DeckBrowserScreen(),
      ));

  void _pickPhoto() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => const PhotoPickerScreen(),
      ));

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final groups = repo.albumGroups();
        if (_category != null && !groups.contains(_category)) _category = null;
        final albums = [
          for (final a in repo.albums)
            if (_category == null || repo.albumGroup(a) == _category) a,
        ];
        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                AlbumTopBar(
                  title: '相片冊',
                  leading: RoundIconButton(
                    label: '返回',
                    icon: const MSvg(MIcon.arrowLeft, size: 20),
                    onTap:
                        widget.onBack ?? () => scope.navigator.selectTab(AppTab.camera),
                  ),
                  trailing: RoundIconButton(
                    label: '搜尋照片',
                    icon: const MSvg(MIcon.search20, size: 20),
                    onTap: _search,
                  ),
                ),
                SizedBox(
                  height: 58,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    children: [
                      for (final c in [null, ...groups]) ...[
                        AlbumPill(
                          label: c ?? '全部',
                          active: c == _category,
                          onTap: () => setState(() => _category = c),
                        ),
                        const SizedBox(width: 8),
                      ],
                    ],
                  ),
                ),
                Expanded(
                  child: GridView.builder(
                    padding: const EdgeInsets.all(MSpace.md),
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 2,
                      mainAxisSpacing: MSpace.sm,
                      crossAxisSpacing: MSpace.sm,
                      mainAxisExtent: 180,
                    ),
                    itemCount: albums.length + 1,
                    itemBuilder: (context, i) {
                      if (i == albums.length) {
                        return _DownloadAlbumTile(
                            hint: repo.albums.isEmpty
                                ? '還沒有相片：去拍照，或到卡片集下載圖片集'
                                : null,
                            onTap: _downloadAlbums);
                      }
                      return _AlbumCard(
                        album: albums[i],
                        cover: repo.albumCoverPhoto(albums[i].id),
                        wordCount: repo.albumWordCount(albums[i].id),
                        waiting: repo
                            .photosInAlbum(albums[i].id)
                            .any((p) => p.awaitingTagging),
                        onTap: () => _openAlbum(albums[i]),
                        onLongPress: () => _rename(albums[i]),
                      );
                    },
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  child: Tap(
                    onTap: _pickPhoto,
                    label: '選擇新照片',
                    child: Container(
                      height: 52,
                      decoration: MDecor.primaryPill(),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const MSvg(MIcon.cameraWhite, size: 20),
                          const SizedBox(width: 8),
                          UiText('選擇新照片',
                              style: MFont.inter(
                                  16, FontWeight.w700, Colors.white)),
                        ],
                      ),
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

/// Figma album-card (17:34): cover, darkening gradient, name, word count.
class _AlbumCard extends StatelessWidget {
  final Album album;
  final Photo? cover;
  final int wordCount;
  final bool waiting;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  const _AlbumCard({
    required this.onLongPress,
    required this.album,
    required this.cover,
    required this.wordCount,
    required this.waiting,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final Widget image = album.coverAsset != null
        ? Image.asset(album.coverAsset!, fit: BoxFit.cover)
        : cover != null
            ? PhotoImage(cover!)
            : const ColoredBox(color: MColors.albumPill);
    return Tap(
      onTap: onTap,
      onLongPress: onLongPress,
      label: '${album.name}，$wordCount 個單字',
      child: Container(
        decoration: BoxDecoration(
          borderRadius: MRadii.rLg,
          boxShadow: MShadows.card,
        ),
        child: ClipRRect(
          borderRadius: MRadii.rLg,
          child: Stack(
            fit: StackFit.expand,
            children: [
              image,
              if (waiting)
                const Positioned(top: 8, right: 8, child: HourglassBadge()),
              // A 卡片集 picture deck says where it came from (問題回報 #403).
              if (album.deckSlug != null)
                Positioned(
                  top: 8,
                  left: 8,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 140),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: MSpace.xs, vertical: 2),
                      decoration: MDecor.softPanel(
                        color: MColors.frost,
                        radius: 10,
                      ),
                      child: UiText(
                          album.author == null
                              ? '卡片集'
                              : '卡片集 · ${album.author}',
                          style: MFont.inter(11, FontWeight.w600, Colors.white)),
                    ),
                  ),
                ),
              const DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    // CSS linear-gradient(226deg, transparent 45%, rgba(0,0,0,.6) 75%)
                    begin: Alignment(0.72, -1),
                    end: Alignment(-0.72, 1),
                    colors: [
                      Color(0x00000000),
                      Color(0x00000000),
                      MColors.photoScrim,
                    ],
                    stops: [0, 0.45, 0.75],
                  ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(MSpace.sm),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(album.name,
                      style: MFont.inter(15, FontWeight.w700, Colors.white)),
                  const SizedBox(height: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: MSpace.xs, vertical: 2),
                    decoration: MDecor.softPanel(
                      color: MColors.frost,
                      radius: 10,
                    ),
                    child: UiText('$wordCount 個單字',
                        style: MFont.inter(11, FontWeight.w600, Colors.white)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      ),
    );
  }
}

/// The last tile of the 相片冊 grid: 下載相片冊 (問題回報 #440).
class _DownloadAlbumTile extends StatelessWidget {
  final String? hint;
  final VoidCallback onTap;

  const _DownloadAlbumTile({required this.onTap, this.hint});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: '下載相片冊',
        child: Container(
          decoration: BoxDecoration(
            color: MColors.albumPill,
            borderRadius: MRadii.rLg,
          ),
          padding: const EdgeInsets.all(MSpace.sm),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.add_rounded, size: 32, color: MColors.primary),
              const SizedBox(height: 4),
              UiText('＋ 下載相片冊',
                  textAlign: TextAlign.center,
                  style: MFont.inter(14, FontWeight.w700, MColors.primary)),
              if (hint != null) ...[
                const SizedBox(height: 6),
                UiText(hint!,
                    textAlign: TextAlign.center,
                    style: MFont.inter(11, FontWeight.w500, MColors.albumMuted)),
              ],
            ],
          ),
        ),
      );
}
