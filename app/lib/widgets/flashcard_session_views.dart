part of '../screens/flashcard_screen.dart';

/// The album and card limits a saved 複習範圍 stands for (問題回報 #412).
/// An album run pushed from the album page ([fixedAlbumId]) keeps its album;
/// a scope whose album is gone falls back to everything.
(String?, Set<String>?) reviewScopeOf(
    WordDatabaseRepository repo, String? fixedAlbumId, String scope) {
  if (fixedAlbumId != null) return (fixedAlbumId, null);
  if (scope == 'new') return (null, repo.cardIdsAddedToday());
  if (scope == 'weak') return (null, repo.weakCardIds());
  if (scope.startsWith('album:')) {
    final id = scope.substring(6);
    if (repo.album(id) != null) return (id, null);
  }
  if (scope.startsWith('deck:')) {
    final deck = DeckLibrary.instance.installedDeck(scope.substring(5));
    if (deck != null) return (null, deckCardIds(repo, deck));
  }
  return (null, null);
}

/// The cards of a downloaded 單字集 (問題回報 #648): a word deck adds words
/// but no 相片冊, so its 複習 tile goes by the words the deck added.
Set<String> deckCardIds(WordDatabaseRepository repo, InstalledDeck deck) => {
      for (final id in deck.wordEntryIds)
        if (repo.cardOf(id) case final c? when !c.archived) c.id,
    };

/// A word deck tile's picture: a photo of one of its words, a different one
/// from the album tiles when it can (and remembered in [used]).
Photo? coverOfDeck(
    WordDatabaseRepository repo, Set<String> ids, Set<String> used) {
  final p = repo.reviewCoverPhoto(ids, avoid: used);
  if (p != null) used.add(p.id);
  return p;
}

/// Downloaded 單字集 (word decks, not picture decks) that have cards.
List<InstalledDeck> _wordDecks(WordDatabaseRepository repo) => [
      for (final d in DeckLibrary.instance.installed)
        if (!d.info.isPhotos && deckCardIds(repo, d).isNotEmpty) d,
    ];

/// Whether keyboard shortcut hints (空白鍵) mean anything: desktop only.
bool _hasKeyboard(BuildContext context) => switch (Theme.of(context).platform) {
      TargetPlatform.windows ||
      TargetPlatform.macOS ||
      TargetPlatform.linux =>
        true,
      _ => false,
    };

/// Short name of a saved 複習範圍 for the picker button.
String reviewScopeLabel(WordDatabaseRepository repo, String scope) {
  if (scope == 'new') return '今天新加的單字';
  if (scope == 'weak') return '弱項單字';
  if (scope.startsWith('album:')) {
    final a = repo.album(scope.substring(6));
    if (a != null) {
      return a.deckSlug != null ? '卡片集：${a.name}' : '相片冊：${a.name}';
    }
  }
  if (scope.startsWith('deck:')) {
    final d = DeckLibrary.instance.installedDeck(scope.substring(5));
    if (d != null) return '單字集：${d.info.title}';
  }
  return '全部';
}

class _Intro extends StatelessWidget {
  final VoidCallback onStart;
  final String? fixedAlbumId;

  const _Intro({required this.onStart, this.fixedAlbumId});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final settings = scope.settings;
    return ListenableBuilder(
      listenable: Listenable.merge([repo, settings]),
      builder: (context, _) {
        final (albumId, cardScope) =
            reviewScopeOf(repo, fixedAlbumId, settings.reviewScope);
        final albumCards =
            albumId == null ? null : repo.cardIdsInAlbum(albumId);
        final probe = FlashcardSession(repo,
            continuous: true, albumId: albumId, cardScope: cardScope);
        final any = !probe.finished;
        probe.dispose();
        // Something to review: pick which book (問題回報 #440).
        if (fixedAlbumId == null && any) return _ScopeGrid(onStart: onStart);
        // 每日上限 (問題回報 #398): today's share, not the whole backlog.
        final today = repo
            .eligibleCards(
                newLimit: settings.dailyNewLimit,
                reviewLimit: settings.dailyReviewLimit)
            .where((c) =>
                (albumCards?.contains(c.id) ?? true) &&
                (cardScope?.contains(c.id) ?? true))
            .length;
        final minutes = math.max(1, (today * 25 / 60).round());
        final waiting = repo.hasCardsWaitingForMeaning;
        return Padding(
          padding: const EdgeInsets.all(MSpace.xl),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                    color: MColors.primarySoft,
                    shape: BoxShape.circle,
                    boxShadow: MShadows.soft,
                    border: Border.all(
                        color: MColors.primary.withValues(alpha: 0.12))),
                child:
                    const Center(child: MSvg(MIcon.tabCardsActive, size: 40)),
              ),
              const SizedBox(height: 20),
              UiText(
                  any
                      ? '想複習的時候就開始吧'
                      : waiting
                          ? '等待詞庫補齊'
                          : '還沒有可以複習的卡片',
                  style: MFont.manrope(20, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 8),
              UiText(
                // Today's capped share, never the overdue backlog (spec: 不顯示欠卡數).
                any
                    ? (today > 0
                        ? '今天 $today 張，約 $minutes 分鐘。做完還可以繼續練習，想休息時按左上角結束。'
                        : '今天的份量已完成。想多練習可以繼續，想休息時按左上角結束。')
                    : waiting
                        ? '單字的{N}意思補齊後，會自動加入複習。'
                        : '在照片詳情挑幾個單字，或下載卡片集，就會變成卡片。',
                textAlign: TextAlign.center,
                style: MFont.manrope(14, FontWeight.w600, MColors.muted),
              ),
              const SizedBox(height: 28),
              if (any)
                PrimaryButton(label: '開始複習', onTap: onStart)
              else ...[
                PrimaryButton(
                  label: '去拍照選單字',
                  onTap: () =>
                      AppScope.of(context).navigator.selectTab(AppTab.camera),
                ),
                const SizedBox(height: 10),
                OutlinedButton(
                  onPressed: () =>
                      AppScope.of(context).navigator.selectTab(AppTab.album),
                  child: const UiText('查看相片冊'),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// 複習 landing (問題回報 #440): one tile per book to review — 綜合 first,
/// then every 相片冊 (own and downloaded) — each with today's due count.
/// Tapping a tile starts that run; the last choice is marked 上次複習.
class _ScopeGrid extends StatelessWidget {
  final VoidCallback onStart;

  const _ScopeGrid({required this.onStart});

  @override
  Widget build(BuildContext context) {
    // Word decks live in the deck library (loaded at start-up, main.dart),
    // not in the repository.
    return ListenableBuilder(
        listenable: DeckLibrary.instance,
        builder: (context, _) => _grid(context));
  }

  Widget _grid(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final settings = scope.settings;
    final due = repo.eligibleCards(
        newLimit: settings.dailyNewLimit,
        reviewLimit: settings.dailyReviewLimit);
    int dueIn(Set<String>? ids) =>
        ids == null ? due.length : due.where((c) => ids.contains(c.id)).length;
    // Album tiles show the album's newest photo; the other tiles a photo of
    // one of their words, a different one from the tiles before when they can.
    final albumTiles = [
      for (final a in repo.albums)
        (
          'album:${a.id}',
          a.name,
          dueIn(repo.cardIdsInAlbum(a.id)),
          a.deckSlug != null,
          repo.albumCoverPhoto(a.id),
          a.coverAsset,
        ),
    ];
    final used = {
      for (final t in albumTiles)
        if (t.$5 case final p?) p.id,
    };
    final deckTiles = [
      for (final d in _wordDecks(repo))
        (
          'deck:${d.info.slug}',
          d.info.title,
          dueIn(deckCardIds(repo, d)),
          true,
          coverOfDeck(repo, deckCardIds(repo, d), used),
          null,
        ),
    ];
    Photo? coverOf(Set<String>? ids) {
      final p = repo.reviewCoverPhoto(ids, avoid: used);
      if (p != null) used.add(p.id);
      return p;
    }

    // (scope, name, due today, from 卡片集, cover photo, bundled cover).
    final allCover = coverOf(null);
    final newIds = repo.cardIdsAddedToday();
    final weakIds = repo.weakCardIds();
    final base = <(String, String, int, bool, Photo?, String?)>[
      ('all', '綜合', dueIn(null), false, allCover, null),
      ...albumTiles,
      ...deckTiles,
      ('new', '今天新加的單字', dueIn(newIds), false, coverOf(newIds), null),
      ('weak', '弱項單字', dueIn(weakIds), false, coverOf(weakIds), null),
    ];
    // A downloaded 單字集 has no photos of its own; its deck cover, if the
    // deck has one, is the tile's picture (問題回報 #648).
    final tiles = [
      for (final t in base)
        (
          t.$1,
          t.$2,
          t.$3,
          t.$4,
          t.$5,
          t.$6,
          t.$1.startsWith('deck:')
              ? switch (DeckLibrary.instance
                  .installedDeck(t.$1.substring(5))
                  ?.info
                  .coverAssetId) {
                  final int id => DeckLibrary.instance.imageUri(id).toString(),
                  _ => null,
                }
              : null,
        ),
    ];
    final saved = settings.reviewScope;
    final last = (saved.startsWith('album:') &&
                repo.album(saved.substring(6)) == null) ||
            (saved.startsWith('deck:') &&
                DeckLibrary.instance.installedDeck(saved.substring(5)) == null)
        ? 'all'
        : saved;
    return ListView(
      padding: const EdgeInsets.all(MSpace.md),
      children: [
        UiText('想複習哪一本？',
            style: MFont.manrope(20, FontWeight.w800, MColors.ink)),
        const SizedBox(height: 4),
        UiText('點一格就開始；做完還可以繼續練習，想休息時按左上角結束。',
            style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
        const SizedBox(height: MSpace.md),
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 2,
          mainAxisSpacing: MSpace.sm,
          crossAxisSpacing: MSpace.sm,
          childAspectRatio: 1.0,
          children: [
            for (final (value, name, count, downloaded, cover, asset, url)
                in tiles)
              Tap(
                label: '$name，今天 $count 張',
                onTap: () {
                  settings.reviewScope = value;
                  onStart();
                },
                child: Container(
                  decoration: BoxDecoration(
                    color: value == 'all' ? MColors.primarySoft : Colors.white,
                    borderRadius: MRadii.rLg,
                    boxShadow: MShadows.card,
                    border: value == last
                        ? Border.all(color: MColors.primary, width: 1.5)
                        : null,
                  ),
                  child: ClipRRect(
                    borderRadius: MRadii.rLg,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // The cover: the album's newest photo, or a photo of
                        // one of the tile's words; a plain block without one.
                        Expanded(
                          child: Stack(
                            fit: StackFit.expand,
                            children: [
                              if (asset != null)
                                Image.asset(asset, fit: BoxFit.cover)
                              else if (cover != null)
                                PhotoImage(cover)
                              else if (url != null)
                                _NetworkCover(url)
                              else
                                ColoredBox(
                                    color: value == 'all'
                                        ? MColors.primarySoft
                                        : MColors.albumPill),
                              Positioned(
                                top: 6,
                                left: 6,
                                right: 6,
                                child: Wrap(
                                  spacing: 4,
                                  runSpacing: 4,
                                  children: [
                                    if (value == last)
                                      const _TileBadge('上次複習',
                                          color: MColors.primary),
                                    if (downloaded)
                                      const _TileBadge('卡片集',
                                          color: MColors.muted),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(
                              MSpace.sm, 6, MSpace.sm, MSpace.sm),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              UiText(name,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: MFont.inter(
                                      15, FontWeight.w700, MColors.ink)),
                              const SizedBox(height: 2),
                              UiText(count > 0 ? '今天 $count 張' : '今天沒有到期',
                                  style: MFont.inter(
                                      12, FontWeight.w600, MColors.muted)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

/// A downloaded deck's cover picture on its 複習 tile (問題回報 #648).
class _NetworkCover extends StatelessWidget {
  final String url;

  const _NetworkCover(this.url);

  @override
  Widget build(BuildContext context) {
    final resolved = resolvePackMedia(url);
    const blank = ColoredBox(color: MColors.albumPill);
    return packMediaIsAsset(resolved)
        ? Image.asset(resolved,
            fit: BoxFit.cover, errorBuilder: (_, __, ___) => blank)
        : Image(
            image: CachedNetworkPhoto(resolved),
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => blank);
  }
}

/// A small label on a 複習 tile's cover (上次複習, 卡片集), readable on a photo.
class _TileBadge extends StatelessWidget {
  final String text;
  final Color color;

  const _TileBadge(this.text, {required this.color});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(10),
        ),
        child: UiText(text, style: MFont.inter(11, FontWeight.w700, color)),
      );
}

/// The end of a run (spec §7's deferred 測驗結束畫面, card #217): how many
/// cards were graded this time, and nothing that nags — no streak, no due
/// or overdue count, no score (spec section 1: 不做連勝、欠卡壓力或罪惡感設計).
/// With nothing graded it only says the run is over.
class _Finished extends StatelessWidget {
  final int reviewed;
  final VoidCallback onDone;

  const _Finished({required this.reviewed, required this.onDone});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(MSpace.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (reviewed > 0)
              Container(
                width: 88,
                height: 88,
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                    color: MColors.primarySoft,
                    shape: BoxShape.circle,
                    boxShadow: MShadows.soft,
                    border: Border.all(
                        color: MColors.primary.withValues(alpha: 0.12))),
                child: const Center(
                    child: Icon(Icons.check_rounded,
                        size: 40, color: MColors.primary)),
              ),
            UiText(reviewed > 0 ? '這次複習了 $reviewed 張卡' : '目前沒有可作答的卡片',
                style: MFont.manrope(22, FontWeight.w800, MColors.ink)),
            const SizedBox(height: 8),
            UiText(
              reviewed > 0
                  ? '辛苦了。每張卡下次出現的時間已經排好，\n想複習時，再回來就好。'
                  : '這次的練習先到這裡。\n想複習時，再回來就好。',
              textAlign: TextAlign.center,
              style: MFont.manrope(14, FontWeight.w600, MColors.muted),
            ),
            const SizedBox(height: 28),
            PrimaryButton(label: '完成', onTap: onDone),
          ],
        ),
      );
}

/// The card under review (front or back) and the fixed bottom bar.
class FlashcardCardView extends StatelessWidget {
  final FlashcardSession session;

  const FlashcardCardView({super.key, required this.session});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    session.guardPhoto();
    final repo = scope.repository;
    final card = session.card!;
    final entry = repo.entry(card.wordEntryId);
    if (entry == null) return const SizedBox.shrink();
    // The usage/sense actually tested this round, so the back shows the
    // same part of speech and meaning as the exercise, not the entry's
    // default usage (問題回報 #4).
    LexemeUsage? activeUsage;
    for (final u in entry.effectiveUsages) {
      if (u.id == session.usageId) {
        activeUsage = u;
        break;
      }
    }
    WordSense? activeSense;
    if (activeUsage != null) {
      for (final s in activeUsage.senses) {
        if (s.id == session.senseId) {
          activeSense = s;
          break;
        }
      }
    }
    // 問題回報：Mac 實機量測翻卡 108ms（M-PERF）: the back is worked out
    // while the front is up, so turning the card does not wait for it.
    if (!session.showingBack) {
      FlashcardBack.prepare(context, repo, entry,
          card: card,
          template: repo.template,
          learnerLevel: repo.profile.cefr,
          activePos: activeUsage?.pos,
          activeDefinition: activeSense?.definition);
    }
    final native = scope.settings.nativeLanguage;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final look = CardLook.of(context);
    return Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
            child: _CardFrame(
                look: look,
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 180),
                  child: session.showingBack
                      ? FlashcardBack(
                          key: ValueKey('back:${card.id}'),
                          entry: entry,
                          activePos: activeUsage?.pos,
                          activeMeaning: activeSense?.meaning,
                          activeDefinition: activeSense?.definition,
                          card: card,
                          photo: session.photo,
                          anchor: session.anchor,
                          photoCredit: session.photoCredit,
                          photos: session.photoOptions,
                          onPhotoSelected: session.selectPhoto,
                          answerCorrect: session.answerCorrect,
                          submittedAnswer: session.submittedAnswer,
                          correctAnswer: session.exercise?.answer,
                          template: repo.template,
                          learnerLevel: repo.profile.cefr,
                          onPlay: () => scope.speakEntry(context, entry,
                              language: repo.language),
                          onOpen: () => scope.navigator.openWord(entry.id),
                        )
                      : FlashcardFront(
                          key: ValueKey('front:${card.id}'),
                          entry: entry,
                          session: session),
                )),
          ),
        ),
        // Fixed at the bottom (spec: 畫面底部固定「顯示答案」／四個評分按鈕).
        Container(
          padding: EdgeInsets.fromLTRB(
              MSpace.lg, MSpace.sm, MSpace.lg, MSpace.md + bottom),
          decoration: look.dock,
          child: session.viewingPrevious
              // 問題回報 #641: the card just graded is shown again; it is
              // not graded twice, the button goes back to the current one.
              ? Column(mainAxisSize: MainAxisSize.min, children: [
                  UiText(
                      session.stepsBack <= 1
                          ? '這是上一張卡片，已經評分過'
                          : '往前第 ${session.stepsBack} 張，已經評分過',
                      style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
                  const SizedBox(height: 6),
                  PrimaryButton(
                      key: const ValueKey('return-to-current'),
                      label: '回到這張卡片',
                      decoration: look.answerButton,
                      height: look.answerHeight,
                      textStyle: look.answerText,
                      onTap: session.returnToCurrent),
                ])
              : session.showingBack
                  ? Column(mainAxisSize: MainAxisSize.min, children: [
                      // 問題回報 #641: look at the question again first.
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          key: const ValueKey('flip-to-front'),
                          style: TextButton.styleFrom(
                              visualDensity: VisualDensity.compact,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                          onPressed: session.canFlipToFront
                              ? session.flipToFront
                              : null,
                          icon: const Icon(Icons.flip_to_front, size: 18),
                          label: const UiText('回到正面'),
                        ),
                      ),
                      RatingBar(
                        previews: session.ratingPreviews,
                        native: native,
                        extraPractice: session.isExtraPractice,
                        onRate: session.rate,
                      ),
                    ])
                  : PrimaryButton(
                      label: '顯示答案',
                      decoration: look.answerButton,
                      height: look.answerHeight,
                      textStyle: look.answerText,
                      // 卡 #226 r112: phones have no space key, so the hint
                      // shows only on desktop.
                      shortcut: session.exercise?.type ==
                                  ReviewExerciseType.photoRecall &&
                              _hasKeyboard(context)
                          ? '空白鍵'
                          : null,
                      onTap: !session.canAnswer
                          ? null
                          : () {
                              if (session.exercise?.type !=
                                  ReviewExerciseType.photoRecall) {
                                session.useHint();
                              }
                              session.showAnswer();
                            }),
        ),
      ],
    );
  }
}

/// The card around the front and the back, in the chosen 卡片樣式
/// (問題回報 #317); the classic style has none.
class _CardFrame extends StatelessWidget {
  final CardLook look;
  final Widget child;

  const _CardFrame({required this.look, required this.child});

  @override
  Widget build(BuildContext context) {
    final card = look.card;
    final accent = look.buttonAccent;
    var framed = child;
    if (accent != null) {
      framed = Theme(
        data: Theme.of(context).copyWith(
          outlinedButtonTheme: OutlinedButtonThemeData(
            style: OutlinedButton.styleFrom(
              foregroundColor: accent,
              minimumSize: const Size(0, 48),
              side: BorderSide(color: accent, width: 1.5),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(look.buttonRadius)),
              textStyle: MFont.manrope(15, FontWeight.w800, accent),
            ),
          ),
        ),
        child: framed,
      );
    }
    if (card == null) return framed;
    return Container(
        key: const ValueKey('card-frame'),
        decoration: card,
        padding: look.cardPadding,
        child: framed);
  }
}

/// A back-of-card section. Longer sections (spec section 5: 較長的相關字、
/// 詞源與來源區塊可預設收合) start [collapsed]; tapping the title opens them.
