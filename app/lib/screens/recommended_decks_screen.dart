import 'dart:async';

import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/deck_library.dart';
import '../services/interest_topics.dart';
import '../services/pack_media.dart' show sizedServerImage;
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/photo_cache.dart' show networkPhoto;

/// 卡 #891: shown once right after 新手引導 — the card sets that fit the
/// learner's interests, goals and level, each with a one-tap 加入, so nobody
/// has to find 相片冊 → 下載相片冊 by themselves. Never an empty page: with no
/// matching deck the basics at the learner's level are listed, and with no
/// connection a short note, 重試 and 略過.
class RecommendedDecksScreen extends StatefulWidget {
  final List<String> interests;
  final List<String> goals;
  final String level;

  /// Tests inject a library with a fake client.
  final DeckLibrary? library;

  const RecommendedDecksScreen({
    super.key,
    this.interests = const [],
    this.goals = const [],
    this.level = 'A1',
    this.library,
  });

  @override
  State<RecommendedDecksScreen> createState() => _RecommendedDecksScreenState();
}

class _RecommendedDecksScreenState extends State<RecommendedDecksScreen> {
  late final DeckLibrary _library = widget.library ?? DeckLibrary.instance;
  List<DeckInfo>? _decks;
  String? _error;
  String? _busy;
  String _progress = '';
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    unawaited(_load());
  }

  Future<void> _load() async {
    final scope = AppScope.of(context);
    setState(() => _error = null);
    try {
      final all = await _library.fetchList(
          target: scope.repository.language,
          native: scope.settings.nativeLanguage);
      if (!mounted) return;
      setState(() => _decks = recommendDecks(all,
          interests: widget.interests,
          goals: widget.goals,
          level: widget.level));
    } on DeckException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _add(DeckInfo info) async {
    final scope = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
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
      messenger
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: UiText('已加入「${info.title}」，可以開始複習')));
    } on DeckException catch (e) {
      messenger
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: UiText(e.message)));
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decks = _decks;
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: _library,
          builder: (context, _) => Column(
            children: [
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
                  children: [
                    UiText('為你挑的相片冊',
                        style: MFont.manrope(24, FontWeight.w800, MColors.ink)),
                    const SizedBox(height: 8),
                    UiText('依你的興趣和程度挑選，一下就能加入；之後也能在「相片冊」找到更多。',
                        style:
                            MFont.manrope(14, FontWeight.w600, MColors.muted)),
                    const SizedBox(height: 20),
                    if (decks == null && _error == null)
                      const Padding(
                        padding: EdgeInsets.all(MSpace.xl),
                        child: Center(child: CircularProgressIndicator()),
                      ),
                    if (_error != null) ...[
                      UiText(_error!,
                          style: const TextStyle(color: MColors.muted)),
                      TextButton(onPressed: _load, child: const UiText('重試')),
                    ],
                    for (final d in decks ?? const <DeckInfo>[])
                      _RecommendedCard(
                        info: d,
                        library: _library,
                        installed: _library.installedDeck(d.slug) != null,
                        busy: _busy == d.slug,
                        progress: _progress,
                        disabled: _busy != null,
                        onAdd: () => _add(d),
                      ),
                  ],
                ),
              ),
              // Outside the scroll view so a short screen never hides it.
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
                child: PrimaryButton(
                    label: _library.installed.isEmpty ? '略過' : '開始使用',
                    onTap: _busy != null
                        ? null
                        : () => Navigator.of(context).maybePop()),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RecommendedCard extends StatelessWidget {
  final DeckInfo info;
  final DeckLibrary library;
  final bool installed;
  final bool busy;
  final bool disabled;
  final String progress;
  final VoidCallback onAdd;

  const _RecommendedCard({
    required this.info,
    required this.library,
    required this.installed,
    required this.busy,
    required this.disabled,
    required this.progress,
    required this.onAdd,
  });

  @override
  Widget build(BuildContext context) {
    final cover = info.coverAssetId;
    return Container(
      margin: const EdgeInsets.only(bottom: MSpace.md),
      decoration: BoxDecoration(
        color: MColors.surface,
        borderRadius: MRadii.rLg,
        border: Border.all(color: const Color(0xFFE9EDF7)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Row(
        children: [
          SizedBox(
            width: 96,
            height: 96,
            child: cover == null
                ? const ColoredBox(color: MColors.primarySoft)
                : Image(
                    image: networkPhoto(sizedServerImage(
                        library.imageUri(cover).toString(),
                        side: 256)),
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        const ColoredBox(color: MColors.primarySoft),
                  ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(MSpace.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  UiText(info.title,
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: MColors.ink)),
                  const SizedBox(height: 2),
                  Text(
                    [
                      if (info.cefr != null) info.cefr!,
                      if (info.topic != null) ui(context, info.topic!),
                      '${info.count} ${ui(context, info.isPhotos ? '張' : '字')}',
                    ].join('　·　'),
                    style: const TextStyle(fontSize: 12, color: MColors.muted),
                  ),
                  const SizedBox(height: MSpace.xs),
                  Align(
                    alignment: Alignment.centerRight,
                    child: busy
                        ? Row(mainAxisSize: MainAxisSize.min, children: [
                            const SizedBox(
                                width: 18,
                                height: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2)),
                            const SizedBox(width: MSpace.xs),
                            Text(progress),
                          ])
                        : installed
                            ? const UiText('已加入')
                            : FilledButton(
                                onPressed: disabled ? null : onAdd,
                                child:
                                    UiText(info.isPhotos ? '加入相片冊' : '加入')),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
