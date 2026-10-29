import 'dart:async';

import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/deck_library.dart';
import '../services/pack_media.dart' show sizedServerImage;
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/photo_cache.dart' show networkPhoto;
import '../services/interest_topics.dart';
import 'photo_grid_screen.dart';

/// 卡片集 (card #323, 問題回報 #320). Layout choice: a full-screen list
/// opened from 設定 and from the top of 單字本 — a fifth tab would crowd the
/// bottom bar, and a deck ends up in 單字本／相片冊 anyway. Each deck is a
/// card (cover, name, CEFR badge, topic, count, author, blurb) with one
/// button: 加入 downloads it into the learner's collection (pictures are kept
/// on the device, so it works offline), 移除 takes it out again.
class DeckBrowserScreen extends StatefulWidget {
  /// Tests inject a library with a fake client.
  final DeckLibrary? library;

  const DeckBrowserScreen({super.key, this.library});

  @override
  State<DeckBrowserScreen> createState() => _DeckBrowserScreenState();
}

class _DeckBrowserScreenState extends State<DeckBrowserScreen> {
  late final DeckLibrary _library = widget.library ?? DeckLibrary.instance;
  List<DeckInfo>? _available;
  String? _error;
  bool _loading = true;
  String? _busy; // slug being added or removed
  String _progress = '';
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    final scope = AppScope.of(context);
    // Also gives picture decks installed before 相片冊 albums their album.
    unawaited(_library.ensureAlbums(scope.repository));
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = AppScope.of(context).repository;
      final decks = await _library.fetchList(
          target: repo.language,
          native: AppScope.of(context).settings.nativeLanguage);
      if (!mounted) return;
      setState(() => _available = decks);
    } on DeckException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _message(String text) => ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: UiText(text)));

  Future<void> _add(DeckInfo info) async {
    final scope = AppScope.of(context);
    setState(() {
      _busy = info.slug;
      _progress = '';
    });
    try {
      final deck = await _library.fetchDeck(info.slug);
      final created = await _library.install(deck,
          repository: scope.repository,
          intake: scope.intake, onProgress: (done, total) {
        if (mounted) setState(() => _progress = '$done/$total');
      });
      if (created.isNotEmpty) unawaited(scope.enricher.process());
      _message('已加入「${info.title}」，可以開始複習');
    } on DeckException catch (e) {
      _message(e.message);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _remove(DeckInfo info) async {
    final scope = AppScope.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: UiText('移除「${info.title}」？'),
        content: const UiText('集合裡的圖片與單字會從你的收藏移除；已經複習過或你編輯過的單字會保留。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const UiText('取消')),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const UiText('移除')),
        ],
      ),
    );
    if (ok != true) return;
    await _library.remove(info.slug, scope.repository);
    _message('已移除「${info.title}」');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: ListenableBuilder(
          listenable: _library,
          builder: (context, _) {
            // Offline, the decks already downloaded stay listed and usable.
            // 新手引導的興趣主題（卡 #814）: matching decks first.
            final shown = sortByInterests(<DeckInfo>[
              ...?_available,
              for (final d in _library.installed)
                if (!(_available ?? const []).any((a) => a.slug == d.info.slug))
                  d.info,
            ], AppScope.of(context).settings.interests);
            return Column(
              children: [
                const MNavBar(title: '卡片集'),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _refresh,
                    child: ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.all(MSpace.md),
                      children: [
                        if (_error != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: MSpace.sm),
                            child: Row(children: [
                              Expanded(
                                  child: UiText(_error!,
                                      style: const TextStyle(
                                          color: MColors.muted))),
                              TextButton(
                                  onPressed: _refresh,
                                  child: const UiText('重試')),
                            ]),
                          ),
                        if (_loading && shown.isEmpty)
                          const Padding(
                            padding: EdgeInsets.all(MSpace.xl),
                            child: Center(child: CircularProgressIndicator()),
                          ),
                        if (!_loading && shown.isEmpty && _error == null)
                          const Padding(
                            padding: EdgeInsets.all(MSpace.xl),
                            child: Center(child: UiText('目前還沒有卡片集')),
                          ),
                        for (final info in shown)
                          _DeckCard(
                            info: info,
                            library: _library,
                            installed:
                                _library.installedDeck(info.slug) != null,
                            busy: _busy == info.slug,
                            progress: _progress,
                            disabled: _busy != null,
                            onAdd: () => _add(info),
                            onRemove: () => _remove(info),
                          ),
                        const SizedBox(height: MSpace.xl),
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _DeckCard extends StatelessWidget {
  final DeckInfo info;
  final DeckLibrary library;
  final bool installed;
  final bool busy;
  final bool disabled;
  final String progress;
  final VoidCallback onAdd;
  final VoidCallback onRemove;

  const _DeckCard({
    required this.info,
    required this.library,
    required this.installed,
    required this.busy,
    required this.disabled,
    required this.progress,
    required this.onAdd,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final albumId = library.installedDeck(info.slug)?.albumId;
    final cover = info.coverAssetId;
    return Container(
      margin: const EdgeInsets.only(bottom: MSpace.md),
      decoration: BoxDecoration(
        color: MColors.surface,
        borderRadius: MRadii.rLg,
        border: Border.all(color: const Color(0xFFE9EDF7)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (cover != null)
            AspectRatio(
              aspectRatio: 16 / 9,
              // 問題回報 #859: kept on disk, the server's smaller copy.
              child: Image(
                image: networkPhoto(sizedServerImage(
                    library.imageUri(cover).toString(),
                    side: 768)),
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    const ColoredBox(color: MColors.primarySoft),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(MSpace.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Expanded(
                    child: UiText(info.title,
                        style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: MColors.ink)),
                  ),
                  if (info.cefr != null) LevelBadge(info.cefr!),
                ]),
                const SizedBox(height: MSpace.xxs),
                Text(
                  [
                    ui(context, info.isPhotos ? '圖片集' : '單字集'),
                    if (info.topic != null) ui(context, info.topic!),
                    '${info.count} ${ui(context, info.isPhotos ? '張' : '字')}',
                    if (info.author != null) ui(context, info.author!),
                  ].join('　·　'),
                  style: const TextStyle(fontSize: 12, color: MColors.muted),
                ),
                if (info.description != null) ...[
                  const SizedBox(height: MSpace.xs),
                  UiText(info.description!,
                      style: const TextStyle(fontSize: 14, color: MColors.ink)),
                ],
                const SizedBox(height: MSpace.sm),
                Align(
                  alignment: Alignment.centerRight,
                  child: busy
                      ? Row(mainAxisSize: MainAxisSize.min, children: [
                          const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2)),
                          const SizedBox(width: MSpace.xs),
                          Text(progress),
                        ])
                      : installed
                          ? Wrap(
                              spacing: MSpace.xs,
                              crossAxisAlignment: WrapCrossAlignment.center,
                              children: [
                                if (albumId != null) ...[
                                  const UiText('已在相片冊'),
                                  OutlinedButton(
                                      onPressed: disabled
                                          ? null
                                          : () => Navigator.of(context).push(
                                                MaterialPageRoute<void>(
                                                  builder: (_) =>
                                                      PhotoGridScreen.album(
                                                          albumId: albumId),
                                                ),
                                              ),
                                      child: const UiText('開啟相簿')),
                                ],
                                OutlinedButton(
                                    onPressed: disabled ? null : onRemove,
                                    child: const UiText('移除')),
                              ],
                            )
                          : FilledButton(
                              onPressed: disabled ? null : onAdd,
                              child: UiText(info.isPhotos ? '加入相片冊' : '加入')),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
