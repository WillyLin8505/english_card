import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'photo_grid_screen.dart';
import 'photo_picker_screen.dart';

/// 我的相片冊 — Figma photo-album-page (17:5), the 相片冊 tab: albums by
/// category, and 選擇新照片.
class AlbumScreen extends StatefulWidget {
  const AlbumScreen({super.key});

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
        final albums = [
          for (final a in repo.albums)
            if (_category == null || a.category == _category) a,
        ];
        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                AlbumTopBar(
                  title: '我的相片冊',
                  leading: RoundIconButton(
                    label: '返回',
                    icon: const MSvg(MIcon.arrowLeft, size: 20),
                    onTap: () => scope.navigator.selectTab(AppTab.camera),
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
                      for (final c in [null, ...albumCategories]) ...[
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
                  child: albums.isEmpty
                      ? Center(
                          child: Text('這個分類還沒有相片冊',
                              style: MFont.inter(
                                  14, FontWeight.w500, MColors.albumMuted)),
                        )
                      : GridView.builder(
                          padding: const EdgeInsets.all(MSpace.md),
                          gridDelegate:
                              const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 2,
                            mainAxisSpacing: MSpace.sm,
                            crossAxisSpacing: MSpace.sm,
                            mainAxisExtent: 180,
                          ),
                          itemCount: albums.length,
                          itemBuilder: (context, i) => _AlbumCard(
                            album: albums[i],
                            cover: repo.albumCoverPhoto(albums[i].id),
                            wordCount: repo.albumWordCount(albums[i].id),
                            waiting: repo
                                .photosInAlbum(albums[i].id)
                                .any((p) => p.awaitingTagging),
                            onTap: () => _openAlbum(albums[i]),
                          ),
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
                          Text('選擇新照片',
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

  const _AlbumCard({
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
                    child: Text('$wordCount 個單字',
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
