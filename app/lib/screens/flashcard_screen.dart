import '../l10n/ui_text.dart';
import 'dart:async';
import 'dart:math' as math;

import '../services/rating_prompt.dart';
import '../services/learning_content.dart';
import 'package:flutter/gestures.dart' show TapGestureRecognizer;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app/app_scope.dart';
import '../models/card_template.dart';
import '../services/accent_audio.dart';
import '../services/deck_library.dart';
import '../services/lexicon_pack.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/flashcard_session.dart';
import '../services/speaker.dart';
import '../services/fsrs_scheduler.dart';
import '../services/word_database_repository.dart';
import '../theme/card_style.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/template_items.dart';
import 'database_library_screen.dart' show DatabaseWordScreen;
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
import '../widgets/mobile/photo_cache.dart'
    show CachedNetworkPhoto, photoProvider;
import '../services/pack_media.dart' show packMediaIsAsset, resolvePackMedia;

part '../widgets/flashcard_session_views.dart';
part '../widgets/flashcard_front.dart';
part '../widgets/flashcard_exercise.dart';
part '../widgets/flashcard_back.dart';
part '../widgets/flashcard_rating.dart';

/// "b _ _ _ _ _ _" — the front's hint: the answer's first letter, one
/// underscore per remaining letter; a phrase keeps its words and spaces
/// (spec section 4: 片語保留單字與空格結構).
String firstLetterHint(String answer) {
  final letter = RegExp(r'\p{L}', unicode: true);
  // A hint must leave something to recall, even for "a" or "I".
  final allowFirstLetter = letter.allMatches(answer).length > 1;
  var shown = false;
  final words = <String>[];
  for (final word in answer.trim().split(RegExp(r'\s+'))) {
    final parts = <String>[];
    for (final ch in word.split('')) {
      if (!letter.hasMatch(ch)) {
        parts.add(ch);
      } else if (shown || !allowFirstLetter) {
        parts.add('_');
      } else {
        parts.add(ch);
        shown = true;
      }
    }
    words.add(parts.join(' '));
  }
  return words.join('   ');
}

/// "3 天" / "2 個月" / "1.5 年" for a grade's next interval.
String intervalLabel(int days) {
  if (days < 30) return '$days 天';
  if (days < 365) return '${(days / 30).round()} 個月';
  return '${(days / 365).toStringAsFixed(1)} 年';
}

/// The 複習 tab — one continuous run using the five exercise types in the
/// learning-template spec. A successful answer reveals the shared card back,
/// then Again / Hard / Good / Easy updates the single FSRS card.
/// There is no due count or score anywhere (spec section 1:
/// 不做連勝、欠卡壓力或罪惡感設計); a thin bar at the top shows how far
/// today's share is (問題回報 #533); the run stops when no card is up.
///
/// Keyboard: Space / Enter shows the answer, 1–4 grade.
class FlashcardScreen extends StatefulWidget {
  /// Set by the shell when another screen asks for a run that starts with
  /// particular cards (學習洞察「複習這些字」); this screen starts the run
  /// and clears it.
  final ValueNotifier<List<String>?>? reviewRequest;

  /// Set when 複習這本相簿 pushes this screen (問題回報 #403): the run only
  /// uses that album's words and pictures, and 返回 goes back to the album.
  final String? albumId;

  const FlashcardScreen({super.key, this.reviewRequest, this.albumId});

  @override
  State<FlashcardScreen> createState() => _FlashcardScreenState();
}

class _FlashcardScreenState extends State<FlashcardScreen> {
  FlashcardSession? _session;
  WordDatabaseRepository? _repo;
  bool _ratingChecked = false;
  bool _wasBack = false;

  // 問題回報 #729: the card on screen (its id, the run's step, and how far
  // back 上一張 is looking), so a change of card stops the old one's sound.
  Object? _audioCard;
  Speaker? _speaker;

  /// The run the learner just left, shown once on the gentle end screen
  /// (spec §7's deferred 測驗結束畫面; card #217; 問題回報 #534). Null when
  /// nothing was graded.
  ReviewRunSummary? _lastRun;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _speaker = AppScope.of(context).speaker;
    final repo = AppScope.of(context).repository;
    if (repo != _repo) {
      // Another learning language: start over.
      _repo = repo;
      _end();
    }
    // A request made before this screen was built.
    if (widget.reviewRequest?.value != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _takeReviewRequest());
    }
  }

  @override
  void initState() {
    super.initState();
    widget.reviewRequest?.addListener(_takeReviewRequest);
  }

  @override
  void didUpdateWidget(FlashcardScreen old) {
    super.didUpdateWidget(old);
    if (old.reviewRequest != widget.reviewRequest) {
      old.reviewRequest?.removeListener(_takeReviewRequest);
      widget.reviewRequest?.addListener(_takeReviewRequest);
    }
  }

  @override
  void dispose() {
    widget.reviewRequest?.removeListener(_takeReviewRequest);
    // 問題回報 #729: leaving the review screen silences its card.
    if (_session != null) _stopAudio();
    _session?.dispose();
    super.dispose();
  }

  void _takeReviewRequest() {
    final request = widget.reviewRequest;
    final ids = request?.value;
    if (request == null || ids == null || !mounted || _repo == null) return;
    // Clear before starting so the notification doesn't come back here.
    request.value = null;
    if (_session != null) _stopAudio();
    _session?.removeListener(_changed);
    _session?.dispose();
    _session = null;
    _lastRun = null;
    _start(focus: ids);
  }

  void _start({List<String> focus = const []}) {
    _ratingChecked = false;
    final scope = AppScope.of(context);
    // A message from another tab (資料庫「已加入…」) would sit on the
    // grade buttons (問題回報 #97).
    ScaffoldMessenger.maybeOf(context)?.removeCurrentSnackBar();
    final (albumId, cardScope) = reviewScopeOf(
        scope.repository, widget.albumId, scope.settings.reviewScope);
    setState(() {
      _session = FlashcardSession(scope.repository,
          continuous: true,
          focus: focus,
          albumId: albumId,
          cardScope: cardScope,
          newLimit: scope.settings.dailyNewLimit,
          reviewLimit: scope.settings.dailyReviewLimit)
        // 問題回報 #693 / #858: a swipe on the back no longer runs the
        // whole precache here (it ranked every card ahead and planned their
        // photos in the middle of the swipe, a dropped frame each page); the
        // pager decodes the pages beside the one shown itself.
        ..addListener(_changed);
      _wasBack = false;
    });
    scope.navigator.setReviewing(true);
    _precacheBackPhoto();
  }

  final _warming = <ImageProvider<Object>>{};
  double? _reviewWidth;

  // Use the same layout and style as the rendered front/back. A photo ID
  // alone is not a cache key: decode size, failed loads and eviction matter.
  void _precacheBackPhoto() {
    final s = _session;
    final width = _reviewWidth;
    if (s == null || width == null) return;
    final scope = AppScope.of(context);
    final look = CardLook.forStyle(scope.settings.cardStyle);
    final contentWidth = math.max(1.0,
        width - 40 - (look.card == null ? 0 : look.cardPadding.horizontal));
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final options = [for (final o in s.photoOptions) o.$1];
    final at = options.indexWhere((o) => o.id == s.photo?.id);
    void warm(ImageProvider<Object>? provider) {
      if (provider == null || !_warming.add(provider)) return;
      precacheImage(provider, context, onError: (_, __) {})
          .whenComplete(() => _warming.remove(provider));
    }

    void warmFront(Photo photo) {
      warm(photoProvider(photo, scope.photoStore,
          Size(contentWidth, look.frontPhotoHeight), dpr));
      // The drag question's photo-shaped frame (usually the same decode
      // size as above, then nothing more is loaded).
      warm(photoProvider(
          photo, scope.photoStore, dragPhotoFrame(photo, contentWidth), dpr,
          fit: BoxFit.contain));
    }

    // 問題回報 #858: at the size of the pager's page (inset beside its
    // neighbours), so the page finds the decoded image in the cache.
    void warmBack(Photo photo, {int index = 0, int count = 1}) =>
        warm(photoProvider(
            photo,
            scope.photoStore,
            photoPagerPageBox(
                Size(contentWidth, look.photoHeight), index, count),
            dpr,
            fit: PinnedPhoto.fitFor(photo, BoxFit.cover),
            thumbnail: true));

    // 問題回報 #726 (單字常常要 loading): every photo used to be decoded at
    // all three sizes — current, swipe neighbours and three cards ahead
    // with two photos each, about 110 MB of pixels on an iPhone — more
    // than the 100 MB image cache, so the next card's photo was often
    // pushed out again before it came up and its front waited 「正在載入
    // 圖片…」. Now only what can show next is decoded, and only at the
    // size it shows at; the cards after that are downloaded, not decoded.
    final count = math.max(1, options.length);
    if (s.photo case final p?) {
      warmFront(p);
      warmBack(p, index: math.max(0, at), count: count);
    }
    // 問題回報 #693: the photos on both sides of the one shown, so a swipe
    // either way lands on a decoded photo.
    for (final i in [
      for (var i = at + 1; i < options.length && i <= at + 3; i++) i,
      if (at > 0) at - 1,
    ]) {
      warmBack(options[i], index: i, count: count);
    }
    // 問題回報 #859: every photo of this card's carousel is on disk before
    // it is swiped to.
    // 問題回報 #944: only the neighbours (a card can have 57 photos).
    for (var i = math.max(0, at - 1);
        i < options.length && i <= math.max(0, at) + 3;
        i++) {
      if (options[i].networkUrl case final url?) {
        CachedNetworkPhoto.prefetch(url);
      }
    }
    final upcoming = s.upcomingCards(cards: 5);
    for (final (i, card) in upcoming.indexed) {
      final photos = s.plannedPhotos(card.wordEntryId);
      if (i < 2 && photos.isNotEmpty) {
        // The next cards' fronts, and their backs once answered.
        warmFront(photos.first);
        warmBack(photos.first);
      }
      // 問題回報 #859: all of the next two cards' photos (their carousels),
      // one for the cards after.
      for (final p in photos.take(i < 2 ? 3 : 1)) {
        if (p.networkUrl case final url?) CachedNetworkPhoto.prefetch(url);
      }
    }
    // 問題回報 #726: the next cards' recordings are downloaded now too, so
    // turning them over does not wait for the server.
    if (_audioPrefetched != s.card?.id) {
      _audioPrefetched = s.card?.id;
      scope.prefetchAudio([
        for (final card in upcoming.take(2))
          if (scope.repository.entry(card.wordEntryId) case final e?)
            if (e.language == 'en')
              for (final accent in const ['en-GB', 'en-US'])
                cardAccentAudioUrl(e, accent)
            else
              e.audioUrl,
      ]);
    }
  }

  String? _audioPrefetched;

  /// Ends the run. With [summary], a run in which at least one card was
  /// graded ends on the end screen instead of straight back at the intro.
  void _end({bool summary = false}) {
    if (_session != null) _stopAudio();
    final run = _session?.summary;
    _session?.removeListener(_changed);
    _session?.dispose();
    _session = null;
    _lastRun = summary && run != null && run.reviewed > 0 ? run : null;
    if (mounted) {
      AppScope.of(context).navigator.setReviewing(false);
      setState(() {});
    }
  }

  void _dismissSummary() => setState(() => _lastRun = null);

  /// Ends the run and leaves an album run's route (back to the album).
  void _leave() {
    _end();
    Navigator.of(context).pop();
  }

  // 問題回報 #262: 誤觸就直接封存、沒有回饋——先確認，封存後給 SnackBar +
  // 復原，呼應相片分頁的復原按鈕.
  Future<void> _deleteCard(String wordEntryId) async {
    final word = AppScope.of(context).repository.entry(wordEntryId)?.word;
    if (word == null) return;
    final confirmed = await showDeleteCardDialog(context, word);
    if (!confirmed) return;
    if (!mounted) return;
    final repo = AppScope.of(context).repository;
    repo.archiveWord(wordEntryId);
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.removeCurrentSnackBar();
    messenger?.showSnackBar(SnackBar(
      content: UiText('已移除「$word」，可在單字本復原'),
      action: SnackBarAction(
        label: ui(context, '復原'),
        onPressed: () => repo.restoreWord(word),
      ),
    ));
  }

  // 問題回報 #316: 學習者直接回報這張卡有問題.
  Future<void> _reportCard(FlashcardSession s) async {
    final scope = AppScope.of(context);
    final entry =
        s.card == null ? null : scope.repository.entry(s.card!.wordEntryId);
    if (entry == null) return;
    final sent = await showCardReportDialog(
      context,
      word: entry.word,
      pos: entry.pos,
      meaning: entry.meaning,
      photoId: s.photo?.id,
      cardType: '${s.exercise?.type.name ?? ''} ${s.showingBack ? '背面' : '正面'}'
          .trim(),
      apiKey: scope.settings.apiKey,
    );
    if (sent == null || !mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.removeCurrentSnackBar();
    messenger?.showSnackBar(
        SnackBar(content: UiText(sent ? '已送出回報，謝謝你' : '已存在這支手機，連上網路後會再送出')));
  }

  void _stopAudio() {
    _audioCard = null;
    if (_speaker case final speaker?) stopCardAudio(speaker);
  }

  void _changed() {
    final s = _session;
    if (s == null || !mounted) return;
    // 問題回報 #729: 切換到下一張（評分、上一張、回到目前這張）時，上一張卡片
    // 的聲音停下，還在下載的錄音和排在後面的另一個腔調也不再播放.
    final card = (s.card?.id, s.reviewed, s.stepsBack);
    if (card != _audioCard) {
      if (_audioCard != null) _stopAudio();
      _audioCard = card;
    }
    // 翻到背面時自動播放單字發音.
    if (s.showingBack && !_wasBack) {
      ScaffoldMessenger.maybeOf(context)?.removeCurrentSnackBar();
      final scope = AppScope.of(context);
      final e =
          s.card == null ? null : scope.repository.entry(s.card!.wordEntryId);
      if (e != null) {
        if (scope.repository.language == 'en') {
          // Card #251: both accents, one after the other (英式、美式各一次).
          playBothAccents(context, e);
        } else {
          scope.speak(context, e.word,
              language: scope.repository.language, audioUrl: e.audioUrl);
        }
      }
    }
    _wasBack = s.showingBack;
    _precacheBackPhoto();
    // The run is over (今天先到這裡): the tab bar comes back.
    if (s.finished) {
      AppScope.of(context).navigator.setReviewing(false);
      // Card #915: a finished run is the good moment (once per version).
      if (!_ratingChecked) {
        _ratingChecked = true;
        unawaited(RatingPrompt.instance?.onReviewCompleted());
      }
    }
    setState(() {});
  }

  KeyEventResult _onKey(FocusNode _, KeyEvent event) {
    final s = _session;
    if (s == null || s.finished || event is! KeyDownEvent) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
    if (!s.showingBack &&
        (key == LogicalKeyboardKey.space || key == LogicalKeyboardKey.enter)) {
      s.showAnswer();
      return KeyEventResult.handled;
    }
    const digits = [
      LogicalKeyboardKey.digit1,
      LogicalKeyboardKey.digit2,
      LogicalKeyboardKey.digit3,
      LogicalKeyboardKey.digit4,
    ];
    final i = digits.indexOf(key);
    if (s.showingBack && i >= 0) {
      s.rate(Rating.values[i]);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final s = _session;
    final look = CardLook.forStyle(scope.settings.cardStyle);
    return Focus(
      autofocus: true,
      onKeyEvent: _onKey,
      child: Scaffold(
        backgroundColor: s == null || s.finished ? MColors.canvas : look.canvas,
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              MNavBar(
                title: '複習',
                sideWidth: s == null || s.finished ? 48 : 112,
                trailingWidth: s == null || s.finished ? 48 : 150,
                // 問題回報 #534: its own node, so 返回 is not merged into the
                // screen once the end screen scrolls.
                leading: Semantics(
                  container: s == null || s.finished,
                  // 卡 #897: the start page of the 複習 tab has no 返回 (it is
                  // the root); a finished run's summary or a pushed album
                  // run keeps it, and the session's own 返回 still ends it.
                  child: s == null
                      ? _lastRun == null && !Navigator.of(context).canPop()
                          ? null
                          : BackNavButton(
                              onTap: _lastRun != null
                                  ? _dismissSummary
                                  : () => Navigator.of(context).pop())
                      : s.finished
                          ? BackNavButton(onTap: () => _end(summary: true))
                          : Row(mainAxisSize: MainAxisSize.min, children: [
                              BackNavButton(onTap: () => _end(summary: true)),
                              const SizedBox(width: 8),
                              // 問題回報 #641: the card just graded, shown again.
                              Opacity(
                                opacity: s.canGoPrevious ? 1 : 0.35,
                                child: NavIconButton(
                                  key: const ValueKey('previous-card'),
                                  label: '上一張卡片',
                                  icon: const Icon(Icons.undo_rounded,
                                      size: 20, color: MColors.label),
                                  onTap: s.canGoPrevious ? s.goPrevious : null,
                                ),
                              ),
                            ]),
                ),
                trailing: s == null || s.finished
                    ? null
                    : Row(children: [
                        NavIconButton(
                          label: '回報此卡片',
                          icon: const Icon(Icons.flag_outlined,
                              size: 20, color: MColors.label),
                          onTap: () => _reportCard(s),
                        ),
                        const SizedBox(width: 8),
                        // 卡 #896: a red ✕ read as "close"; this moves the card
                        // to 已學會, so say so with a check icon and text.
                        // French 「Acquis」 is wider than the 150px slot (375pt).
                        Flexible(
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerRight,
                            child: Tap(
                              key: const ValueKey('mark-learned'),
                              label: '標為已學會',
                              labelOnly: true,
                              onTap: () {
                                final card = s.card;
                                if (card != null) {
                                  _deleteCard(card.wordEntryId);
                                }
                              },
                              child: Container(
                                height: 48,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 10),
                                decoration: MDecor.softPanel(
                                    color: MColors.surfaceSoft,
                                    radius: MRadii.sm),
                                child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const Icon(Icons.check_circle_outline,
                                          size: 18, color: MColors.label),
                                      const SizedBox(width: 4),
                                      UiText('已學會',
                                          style: MFont.cjk(13, FontWeight.w700,
                                              MColors.label)),
                                    ]),
                              ),
                            ),
                          ),
                        ),
                      ]),
              ),
              Expanded(
                child: s == null
                    ? _lastRun != null
                        ? _Finished(run: _lastRun!, onDone: _dismissSummary)
                        : _Intro(onStart: _start, fixedAlbumId: widget.albumId)
                    : s.finished
                        ? _Finished(
                            run: s.summary,
                            onDone: widget.albumId != null ? _leave : _end)
                        // 問題回報 #533: the progress bar lies over the top
                        // edge, so nothing below it moves.
                        : Stack(children: [
                            Positioned.fill(
                              child: CardLookScope(
                                  look: look,
                                  child: LayoutBuilder(
                                      builder: (context, constraints) {
                                    _reviewWidth = constraints.maxWidth;
                                    _precacheBackPhoto();
                                    return FlashcardCardView(session: s);
                                  })),
                            ),
                            if (s.progressTotal > 0)
                              Positioned(
                                  top: 0,
                                  left: 0,
                                  right: 0,
                                  child: ReviewProgressBar(
                                      done: s.progressDone,
                                      total: s.progressTotal)),
                          ]),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
