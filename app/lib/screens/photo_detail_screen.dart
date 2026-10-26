import '../l10n/ui_text.dart';
import '../services/learning_content.dart';
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import '../services/lexicon_pack.dart';
import '../services/photo_intake.dart' show TaggingNotConfigured;
import '../services/photo_word_grid.dart';
import '../services/photo_word_session.dart';
import '../services/word_database_repository.dart';
import '../services/word_selector.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
import '../widgets/mobile/photo_word_grid_table.dart';

part '../widgets/photo_word_cards.dart';
part '../widgets/photo_difficulty_controls.dart';

/// The dial's wording next to the CEFR level (spec section 3: 輪盤中心
/// 同時顯示文字與 CEFR 範圍，避免只靠顏色判斷).
String relativeDifficulty(int offset) => switch (offset) {
      <= -2 => '很簡單',
      -1 => '簡單',
      0 => '剛好',
      1 => '稍難',
      _ => '挑戰',
    };

/// 照片詳情 — Figma photo-detail-view (24:4) and its expanded difficulty
/// state (54:77): the photo with its word pins, the difficulty dial, and
/// the 辨識單字列表.
///
/// Spec section 7 (照片選詞與標籤操作): the list holds at most five
/// suggested words picked on this device from the AI's candidates. Swipe
/// a word left when you already know it (已學會); ☆ keeps a word while
/// the dial moves; drag a pin to put it on the right spot; tap a pin to
/// correct it or delete a wrong one; 自己加字 adds a word the AI missed,
/// placed with a tap on the photo (問題回報 #323). There is no 建立 button
/// — leaving the page saves the list and creates the cards.
class PhotoDetailScreen extends StatefulWidget {
  final String photoId;

  const PhotoDetailScreen({super.key, required this.photoId});

  @override
  State<PhotoDetailScreen> createState() => _PhotoDetailScreenState();
}

class _PhotoDetailScreenState extends State<PhotoDetailScreen>
    with WidgetsBindingObserver {
  /// A word in the learning language's spelling (French lowercase with its
  /// article, 問題回報 #499); English stays capitalised.
  String _shown(String word, String? pos) => shownWord(
      word, AppScope.of(context).repository.language,
      pos: pos);

  AppScope? _scope;
  PhotoWordSession? _session;
  bool _visible = false;

  /// 問題回報 #490: the word list (cards, lookups, swipe wrappers) is built one
  /// frame after the photo, so opening the page doesn't hitch on iPhone 12.

  /// An added word waiting for a tap on the photo to get its pin.
  SessionWord? _placing;

  /// 長按辨識 (問題回報 #616, #690): spots long-pressed one after another.
  /// [_toScan] wait for the AI — sent one at a time, [_scanningNow] is on
  /// its way — and [_answered] wait, in order, for the learner to pick a
  /// word; one sheet at a time ([_choosing]), the next opens when it closes.
  final List<LabelPoint> _toScan = [];
  LabelPoint? _scanningNow;
  final List<(LabelPoint, List<WordCandidate>)> _answered = [];
  bool _choosing = false;

  /// 問題回報 #709: a tap on the photo hides the labels; another shows them.
  bool _pinsHidden = false;
  final _photoKey = GlobalKey();

  /// 問題回報：Mac 實機量測照片詳情開啟 114ms（M-PERF）: the whole page in its
  /// first frame took up to 96 ms to build. Frame 0 is the photo and the
  /// title; frame 1 picks the words and draws the labels; frame 2 adds the
  /// difficulty bar and the words; frame 3 the rest under the list.
  /// 問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）: each
  /// step rebuilt the whole page, and the list frame (an IconButton per
  /// word) was still the heaviest. Now each part shows itself
  /// ([_AfterFrames]) without rebuilding the rest: frame 2 the bar and the
  /// list title, frames 3 and 4 two words each (the first ones are what a
  /// phone shows under the photo), frame 5 the fifth, frames 6 and 7 what
  /// is under the list.
  bool _started = false;
  bool _opening = true;

  /// Word cards per frame (M-PERF2): each has an IconButton and two icon
  /// buttons, about 2 ms each to build in the tests.
  static const _wordsPerFrame = 2;

  /// Frames after the labels before a part shows, while the page opens;
  /// afterwards (a word added, the list re-picked) at once.
  int _after(int frames) => _opening ? frames : 0;

  /// Meanings with their 片語/… tag and IPA from the word list, kept until
  /// the repository or the pack changes (M-PERF: they were looked up for
  /// every label on every rebuild, e.g. each step of the difficulty bar).
  final Map<(String, String, String), String> _zhCache = {};
  final Map<String, String?> _ipaCache = {};
  Listenable? _cacheSource;
  WordDatabaseRepository? _cacheRepo;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _advanceAfterFrame();
  }

  void _advanceAfterFrame() =>
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        // Between frames, so neither frame pays for the word picking.
        _startSession();
        setState(() => _started = true);
        _endOpening(7);
      });

  void _endOpening(int frames) =>
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (frames > 1) {
          _endOpening(frames - 1);
          WidgetsBinding.instance.scheduleFrame();
        } else {
          _opening = false;
        }
      });

  void _startSession() {
    final scope = _scope;
    if (scope == null || _session != null) return;
    _session = PhotoWordSession(
      repo: scope.repository,
      photoId: widget.photoId,
      queue: scope.queue,
    )
      ..addListener(_changed)
      // 問題回報 #666: 多看動詞／難一點 that finds nothing says so.
      ..onNotice = _showNotice;
  }

  void _showNotice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: UiText(message)));
  }

  void _clearCaches() {
    _zhCache.clear();
    _ipaCache.clear();
  }

  /// [meaning] with its entry type from the pack, as labels show it.
  String _zh(String word, String pos, String meaning) => _zhCache.putIfAbsent(
      (word, pos, meaning),
      () => typedMeaning(
          meaning,
          LexiconPack.instance.lookup(word, pos: pos)?.entry.entryType ??
              'word'));

  String? _ipa(WordDatabaseRepository repo, String word) =>
      _ipaCache.putIfAbsent(word, () => repo.entryByWord(word)?.ipa);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final scope = _scope = AppScope.of(context);
    if (!identical(scope.repository, _cacheRepo)) {
      _cacheSource?.removeListener(_clearCaches);
      _cacheRepo = scope.repository;
      _cacheSource = Listenable.merge([scope.repository, LexiconPack.instance])
        ..addListener(_clearCaches);
      _clearCaches();
    }
    // Leaving by any navigation saves: another tab, a screen on top.
    final visible =
        (ActiveTabScope.of(context) ?? AppTab.album) == AppTab.album &&
            (ModalRoute.of(context)?.isCurrent ?? true);
    if (_visible && !visible) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _save());
    }
    _visible = visible;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _save();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cacheSource?.removeListener(_clearCaches);
    final session = _session;
    final scope = _scope;
    if (session != null) {
      session.removeListener(_changed);
      // Not while the tree is being torn down: other screens rebuild.
      scheduleMicrotask(() {
        _saveWith(session, scope);
        session.dispose();
      });
    }
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _save() => _saveWith(_session, _scope);

  static void _saveWith(PhotoWordSession? session, AppScope? scope) {
    if (session == null || scope == null) return;
    final result = session.save();
    if (result.created.isNotEmpty) unawaited(scope.enricher.process());
  }

  // ── Pins ──────────────────────────────────────────────────────────

  Future<void> _openWord(SessionWord w) async {
    final scope = AppScope.of(context);
    _save();
    final e = scope.repository.entryByWord(w.word);
    if (e != null) scope.navigator.openWord(e.id);
  }

  Future<void> _pinActions(SessionWord w) async {
    final session = _session!;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text('${_shown(w.word, w.candidate.pos)}　${w.candidate.meaning}',
                  style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
              subtitle: const UiText('可查看意思、改成正確的字、刪除或標為已學會。'),
            ),
            ListTile(
              leading: const Icon(Icons.menu_book_outlined),
              title: const UiText('查看單字'),
              onTap: () => Navigator.pop(context, 'open'),
            ),
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const UiText('修改標籤'),
              onTap: () => Navigator.pop(context, 'edit'),
            ),
            if (!w.placed)
              ListTile(
                leading: const Icon(Icons.push_pin_outlined),
                title: const UiText('放到照片上'),
                onTap: () => Navigator.pop(context, 'place'),
              ),
            ListTile(
              leading: const Icon(Icons.delete_outline),
              title: const UiText('刪除（照片裡沒有這個）'),
              onTap: () => Navigator.pop(context, 'delete'),
            ),
            ListTile(
              leading: const Icon(Icons.check_circle_outline,
                  color: MColors.success),
              title: const UiText('我已經會了（移到已學會）'),
              onTap: () => Navigator.pop(context, 'known'),
            ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    switch (action) {
      case 'open':
        await _openWord(w);
      case 'edit':
        final lexicon = AppScope.of(context).lexicon;
        final result = await showLabelDialog(
          context,
          title: '修改標籤',
          word: w.word,
          zh: w.candidate.meaning,
          hint: '改了英文、中文沒改，會改用詞庫的意思。',
        );
        if (result != null) {
          final level = lexicon.resolve(result.word, w.candidate.pos).level;
          session.correct(w,
              word: result.word, meaning: result.zh, level: level);
        }
      case 'place':
        setState(() => _placing = w);
      case 'delete':
        session.delete(w);
        if (_placing == w) setState(() => _placing = null);
        showToast(context, '已刪除「${_shown(w.word, w.candidate.pos)}」，這張照片不會再推薦它');
      case 'known':
        session.swipe(w);
    }
  }

  /// 自己加字: the word, then a tap on the photo for its pin (or none).
  Future<void> _addWord() async {
    final scope = AppScope.of(context);
    final session = _session!;
    final result = await showLabelDialog(
      context,
      title: '自己加字',
      hint: '中文可以留空，會用詞庫的意思。',
    );
    if (result == null || !mounted) return;
    final word = LexiconPack.normalize(result.word);
    final level = scope.lexicon
        .resolve(word, word.contains(' ') ? 'phrase' : 'noun')
        .level;
    final w = session.add(word: word, meaning: result.zh, level: level);
    if (w == null) return;
    setState(() => _placing = w.placed ? null : w);
    // 自己加字 sits under the list (問題回報 #438): bring the photo and its
    // 「點一下放位置」 bar back into view so the learner can place the pin.
    if (_placing == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final photo = _photoKey.currentContext;
      if (photo != null && photo.mounted) {
        Scrollable.ensureVisible(photo,
            duration: const Duration(milliseconds: 250));
      }
    });
  }

  /// 長按辨識 (問題回報 #616): long-press anywhere on the photo → that part
  /// of the picture goes to the AI → the learner picks the word → it is
  /// pinned at that spot (and saved like 自己加字).
  ///
  /// 問題回報 #690: several spots can be long-pressed in a row. Each shows a
  /// ring at once and joins a queue; the AI is asked about them one at a
  /// time. Answered spots turn into numbered markers and their choices
  /// open one after another, in the order they were pressed.
  void _recognizeAt(Photo photo, LabelPoint at) {
    // The same spot twice (a finger resting) is one spot.
    bool near(LabelPoint p) =>
        (p.x - at.x).abs() < 0.03 && (p.y - at.y).abs() < 0.03;
    if ([
      ..._toScan,
      if (_scanningNow case final now?) now,
      for (final a in _answered) a.$1,
    ]
        .any(near)) {
      return;
    }
    setState(() => _toScan.add(at));
    if (_scanningNow == null) unawaited(_scanNext(photo));
  }

  Future<void> _scanNext(Photo photo) async {
    while (mounted && _toScan.isNotEmpty) {
      final at = _toScan.first;
      setState(() {
        _toScan.removeAt(0);
        _scanningNow = at;
      });
      try {
        final found = await AppScope.of(context).queue.recognizeSpot(photo, at);
        if (!mounted) return;
        setState(() {
          _scanningNow = null;
          _answered.add((at, found));
        });
        unawaited(_chooseNext());
      } on TaggingNotConfigured {
        if (!mounted) return;
        // No recognizer: none of the waiting spots can be answered.
        setState(_toScan.clear);
        showToast(context, '還沒設定照片辨識：到 設定 → 進階設定 → 照片辨識連線');
      } catch (e) {
        debugPrint('長按辨識失敗: $e');
        if (mounted) showToast(context, '辨識失敗，請檢查網路後再試');
      } finally {
        if (mounted) setState(() => _scanningNow = null);
      }
    }
  }

  /// Opens the choices of the first answered spot, then the next one.
  Future<void> _chooseNext() async {
    if (_choosing) return;
    _choosing = true;
    try {
      while (mounted && _answered.isNotEmpty) {
        final (at, found) = _answered.first;
        await _chooseFor(at, found);
        if (!mounted) return;
        setState(() => _answered.removeAt(0));
      }
    } finally {
      _choosing = false;
    }
  }

  Future<void> _chooseFor(LabelPoint at, List<WordCandidate> found) async {
    final scope = AppScope.of(context);
    final session = _session;
    if (session == null) return;
    final onPhoto = {for (final w in session.words) w.word};
    final choices = found.take(6).toList();
    // Other spots still waiting after this one.
    final more = _answered.length - 1 + _toScan.length +
        (_scanningNow == null ? 0 : 1);
    final picked = await showModalBottomSheet<Object>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ListTile(
                leading: const _SpotNumber(1),
                title: UiText(choices.isEmpty ? 'AI 在這裡沒有認出東西' : 'AI 在這裡看到',
                    style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                subtitle: UiText(choices.isEmpty
                    ? '可以換個位置再長按，或自己輸入。'
                    : '選一個字，就會在照片上標 1 的位置加上標籤。'),
              ),
              for (final c in choices)
                ListTile(
                  key: ValueKey('spot-${c.word}'),
                  title: Text('${_shown(c.word, c.pos)}　${c.meaning}',
                      style: MFont.manrope(15, FontWeight.w700, MColors.ink)),
                  subtitle: UiText(onPhoto.contains(c.word)
                      ? '已在照片上，選它會移到這裡'
                      : levelLabel(c.level)),
                  trailing: UiText(onPhoto.contains(c.word) ? '移到這裡' : '加入',
                      style:
                          MFont.manrope(14, FontWeight.w800, MColors.primary)),
                  onTap: () => Navigator.pop(context, c),
                ),
              ListTile(
                leading: const Icon(Icons.edit_outlined),
                title: const UiText('都不是，自己輸入'),
                onTap: () => Navigator.pop(context, 'manual'),
              ),
              if (more > 0)
                ListTile(
                  key: const ValueKey('spot-skip'),
                  leading: const Icon(Icons.skip_next_outlined),
                  title: UiText('略過，看下一個位置（還有 $more 個）'),
                  onTap: () => Navigator.pop(context),
                ),
            ],
          ),
        ),
      ),
    );
    if (picked == null || !mounted) return;
    if (picked is WordCandidate) {
      final w = session.addFound(picked, at);
      showToast(context, '已在這個位置加上「${_shown(w.word, w.candidate.pos)}」');
      return;
    }
    final result = await showLabelDialog(
      context,
      title: '自己加字',
      hint: '中文可以留空，會用詞庫的意思。',
    );
    if (result == null || !mounted) return;
    final word = LexiconPack.normalize(result.word);
    final level = scope.lexicon
        .resolve(word, word.contains(' ') ? 'phrase' : 'noun')
        .level;
    session.add(word: word, meaning: result.zh, level: level, at: at);
  }

  void _placeAt(LabelPoint at) {
    final w = _placing;
    if (w == null) return;
    _session!.move(w, at);
    setState(() => _placing = null);
  }

  // ── Difficulty bar (問題回報 #442) ───────────────────────────────

  /// While the thumb moves: only the photo's current pool is re-picked.
  void _moveBar(int i) => _session!.setTarget(i, live: true);

  /// A tap, or the end of a drag: the model may be asked for more words.
  void _settleBar(int i) => _session!.setTarget(i);

  // ── Build ─────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: Listenable.merge([repo, scope.queue]),
      builder: (context, _) {
        final photo = repo.photo(widget.photoId);
        if (photo == null) {
          return Scaffold(
            backgroundColor: MColors.canvas,
            body: SafeArea(
              child: Column(
                children: [
                  const MNavBar(title: '照片詳情', leading: BackNavButton()),
                  Expanded(
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(MSpace.xxl),
                        child: UiText(
                          '這張照片已從相片冊移除。\n手機相簿裡的原始照片不受影響。',
                          textAlign: TextAlign.center,
                          style:
                              MFont.manrope(15, FontWeight.w700, MColors.muted),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        }
        final session = _started ? _session : null;
        final old = session != null && session.showLearned
            ? session.oldWords
            : const <OldWord>[];
        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                MNavBar(
                  title: '照片詳情',
                  leading: const BackNavButton(),
                  trailing: ShareNavButton(
                    onTap: () => SharePlus.instance.share(ShareParams(
                      title: photo.title,
                      text: '${ui(context, '照片裡的{L}單字：')}'
                          '${(_session?.words ?? const <SessionWord>[]).map((w) => '${_shown(w.word, w.candidate.pos)} ${w.candidate.meaning}').join('、')}',
                    )),
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Padding(
                          key: _photoKey,
                          padding: const EdgeInsets.all(MSpace.md),
                          child: Container(
                            // 問題回報 #664: the whole photo, at its shape.
                            height: PinnedPhoto.frameHeight(
                                photo,
                                MediaQuery.sizeOf(context).width -
                                    2 * MSpace.md,
                                maxHeight:
                                    MediaQuery.sizeOf(context).height * 0.62),
                            decoration:
                                MDecor.heroPhotoFrame(radius: MRadii.xxl),
                            clipBehavior: Clip.antiAlias,
                            child: session == null
                                // M-PERF: frame 0 — the photo alone, as
                                // PinnedPhoto draws it (labels come next).
                                ? ClipRRect(
                                    borderRadius: BorderRadius.circular(24),
                                    child: RepaintBoundary(
                                        child: PhotoImage(photo,
                                            fit: PinnedPhoto.fitFor(
                                                photo, BoxFit.contain))),
                                  )
                                : Stack(
                                    children: [
                                      Positioned.fill(
                                          child: _pinnedPhoto(
                                              photo, session, old)),
                                      if (_pinsHidden && _placing == null)
                                        const _PinsHiddenChip(),
                                    ],
                                  ),
                          ),
                        ),
                        if (session != null) ...[
                          _AfterFrames(
                            frames: _after(1),
                            child: PhotoDifficultyBar(
                              key: const ValueKey('difficulty-bar'),
                              target: session.target,
                              offset: session.offset,
                              onMove: _moveBar,
                              onSelect: _settleBar,
                            ),
                          ),
                          _AfterFrames(
                            frames: _after(1),
                            child: _levelRow(photo, session),
                          ),
                          if (_placing case final w?)
                            _PlacingBar(
                              word: _shown(w.word, w.candidate.pos),
                              onSkip: () => setState(() => _placing = null),
                            ),
                          _buildList(photo, session, old),
                          // M180 (owner #732): 詞性 × CEFR, under everything
                          // else so nothing above moves.
                          _AfterFrames(
                            frames: _after(6),
                            child: _wordGrid(photo, session, old),
                          ),
                        ],
                      ],
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

  Widget _pinnedPhoto(
      Photo photo, PhotoWordSession session, List<OldWord> old) {
    final pins = [
      for (final w in session.words)
        if (w.placed)
          PinData(
            id: w.word,
            anchor: w.anchor,
            word: _shown(w.word, w.candidate.pos),
            zh: _zh(w.word, w.candidate.pos, w.candidate.meaning),
            linked: w.candidate.inDatabase || LexiconPack.instance.isEmpty,
            // A word read off the photo is framed where it is printed,
            // until the learner drags its label somewhere else.
            frame: w.candidate.box?.contains(w.anchor) == true
                ? w.candidate.box
                : null,
          ),
      for (final o in old)
        PinData(
          id: 'old:${o.word}',
          anchor: o.anchor,
          word: _shown(o.word, o.candidate.pos),
          zh: _zh(o.word, o.candidate.pos, o.candidate.meaning),
          muted: true,
        ),
    ];
    SessionWord? wordOf(PinData p) =>
        session.words.where((w) => w.word == p.id).firstOrNull;
    return PinnedPhoto(
      photo: photo,
      pins: pins,
      onPinTap: (p) {
        final w = wordOf(p);
        if (w != null) _pinActions(w);
      },
      onPinMoved: (p, to) {
        final w = wordOf(p);
        if (w != null) session.move(w, to);
      },
      // 放位置 comes first; otherwise a tap hides or shows the labels
      // (問題回報 #709).
      onPhotoTap: _placing == null
          ? (_) => setState(() => _pinsHidden = !_pinsHidden)
          : _placeAt,
      onPhotoLongPressAt: (at) => _recognizeAt(photo, at),
      scanningSpots: [
        if (_scanningNow case final now?) now,
        ..._toScan,
      ],
      waitingSpots: [for (final a in _answered) a.$1],
      hidePins: _pinsHidden && _placing == null,
      overlay: _overlayFor(photo, session),
      revealNew: true,
      fit: BoxFit.contain,
    );
  }

  Widget? _overlayFor(Photo photo, PhotoWordSession session) {
    final scope = AppScope.of(context);
    if (scope.queue.current == photo.id ||
        (photo.taggingStatus == TaggingStatus.tagging &&
            photo.candidates.isEmpty)) {
      // 問題回報 #409: a light bar sweeps the photo while it is read.
      return const Stack(
        children: [
          _PhotoBadgeOverlay(icon: null, text: 'AI 辨識中…'),
          Positioned.fill(child: PhotoScanSweep()),
        ],
      );
    }
    if (photo.taggingStatus == TaggingStatus.pending &&
        photo.candidates.isEmpty) {
      // Not set up is not "in progress": say so instead of an hourglass.
      return scope.settings.taggingConfigured
          ? const _PhotoBadgeOverlay(
              icon: Icons.hourglass_top_rounded, text: '等待 AI 辨識')
          : const _PhotoBadgeOverlay(
              icon: Icons.link_off_rounded, text: '這台裝置沒有照片辨識');
    }
    return null;
  }

  /// 問題回報 #674: the label options (多看動詞、難一點、重新掃描…) sit right
  /// under the difficulty bar they go with, not below the word list (#451).
  Widget _levelRow(Photo photo, PhotoWordSession session) {
    final topping = AppScope.of(context).queue.isToppingUp(photo.id);
    // 問題回報 #675: a harder setting than any word the AI found here shows
    // fewer words; say why and how to get harder ones.
    final hardest = photo.candidates.isEmpty
        ? -1
        : photo.candidates
            .map((c) => levelIndex(c.level))
            .reduce((a, b) => a > b ? a : b);
    final short = hardest >= 0 && session.target > hardest;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (short)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: UiText(
                  'AI 在這張照片找到的字最難到「${levelName(cefrLevels[hardest])}」，按「重新掃描標籤」請 AI 找更難的字',
                  key: const ValueKey('level-short-hint'),
                  style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
            ),
          _LevelRow(
          bias: session.bias,
          busy: topping ||
              session.fetchingMore != null ||
              session.rescanning,
          busyLabel: session.rescanning
              ? 'AI 正在重新掃描…'
              : session.fetchingMore == null
                  ? null
                  : 'AI 正在找更多${PhotoWordSession.focusLabel(session.fetchingMore!)}…',
          onBias: session.setBias,
          // 問題回報 #670: read the whole photo again.
          onRescan: session.rescanning ? null : session.rescan,
        ),
        ],
      ),
    );
  }

  Widget _buildList(Photo photo, PhotoWordSession session, List<OldWord> old) {
    final scope = AppScope.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _AfterFrames(
            frames: _after(1),
            child: Row(
              children: [
                Expanded(
                  child: UiText('辨識單字列表 (${session.words.length})',
                      style: MFont.manrope(15, FontWeight.w800, MColors.muted)),
                ),
                UiText('顯示已學會單字',
                    style: MFont.manrope(12, FontWeight.w700, MColors.label)),
                Transform.scale(
                  scale: 0.75,
                  child: Switch(
                    value: session.showLearned,
                    onChanged: session.setShowLearned,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          if (session.words.isEmpty)
            _AfterFrames(frames: _after(1), child: _emptyState(photo, session)),
          for (final (i, w) in session.words.indexed) ...[
            _AfterFrames(
              key: ValueKey('shown:${w.word}'),
              frames: _after(math.min(4, 2 + i ~/ _wordsPerFrame)),
              child: Dismissible(
                key: ValueKey('word:${w.word}'),
                direction: DismissDirection.endToStart,
                background: const _KnownBackground(),
                onDismissed: (_) {
                  final undo = OldWord(w.candidate, w.anchor, learned: true);
                  session.swipe(w);
                  // 問題回報 #299: 和複習畫面一樣，提示帶「復原」按鈕.
                  ScaffoldMessenger.of(context)
                    ..hideCurrentSnackBar()
                    ..showSnackBar(SnackBar(
                      content: UiText('已把「${_shown(w.word, w.candidate.pos)}」移到已學會'),
                      action: SnackBarAction(
                        label: ui(context, '復原'),
                        onPressed: () => session.restore(undo),
                      ),
                    ));
                },
                child: _WordCard(
                  word: _shown(w.word, w.candidate.pos),
                  ipa: w.candidate.ipa ?? _ipa(scope.repository, w.word),
                  zh: _zh(w.word, w.candidate.pos, w.candidate.meaning),
                  level: w.candidate.level,
                  starred: w.starred,
                  onTap: () => _openWord(w),
                  onMore: () => _pinActions(w),
                  onAudio: () => scope.speak(context, w.word,
                      language: scope.repository.language),
                  onStar: () => session.toggleStar(w),
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          // M-PERF: what follows the words is below the fold; one frame later
          // (M-PERF2: the shortcuts, then the notes under them).
          _AfterFrames(
            frames: _after(5),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 問題回報 #438: adding a missed word comes after reading the list.
                Row(
                  children: [
                    TextButton.icon(
                      key: const ValueKey('add-word'),
                      onPressed: _addWord,
                      icon: const Icon(Icons.add_rounded, size: 18),
                      label: UiText('自己加字',
                          style: MFont.manrope(
                              13, FontWeight.w800, MColors.primary)),
                    ),
                    // 問題回報 #616: the other way to add a word.
                    Expanded(
                      child: UiText('或在照片上長按，讓 AI 認那個位置',
                          maxLines: 2,
                          style: MFont.manrope(
                              12, FontWeight.w600, MColors.muted)),
                    ),
                  ],
                ),
              ],
            ),
          ),
          _AfterFrames(
            frames: _after(6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 問題回報 #276: the "no 建立 button, leaving saves" rule used to sit
                // under all five words; #451 (owner 10/21) moved it below the list too.
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Icon(Icons.check_circle_outline_rounded,
                        size: 14, color: MColors.label),
                    const SizedBox(width: 4),
                    Expanded(
                      child: UiText('返回時自動保存，不用再按建立。',
                          style: MFont.manrope(
                              12, FontWeight.w600, MColors.label)),
                    ),
                  ],
                ),
                if (old.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  const SectionLabel('已學會與學習中的舊詞'),
                  const SizedBox(height: 8),
                  for (final o in old) ...[
                    _OldWordRow(
                      word: _shown(o.word, o.candidate.pos),
                      zh: _zh(o.word, o.candidate.pos, o.candidate.meaning),
                      learned: o.learned,
                      onRestore: o.learned
                          ? () {
                              session.restore(o);
                              showToast(context, '已復原「${_shown(o.word, o.candidate.pos)}」');
                            }
                          : null,
                    ),
                    const SizedBox(height: 8),
                  ],
                ],
                const SizedBox(height: 4),
                UiText(
                  '左滑單字表示已經會了；拖曳照片上的標籤可調整位置；點標籤可改字或刪除。',
                  textAlign: TextAlign.center,
                  style: MFont.manrope(12, FontWeight.w600, MColors.label),
                ),
                if (session.selection != null &&
                    session.selection!.scored.isNotEmpty)
                  Center(
                    child: TextButton(
                      onPressed: () =>
                          showSelectionReasons(context, session.selection!),
                      child: UiText('為什麼是這些字？',
                          style: MFont.manrope(
                              12, FontWeight.w700, MColors.primary)),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── 詞性 × CEFR 表格 (M180) ─────────────────────────────────────

  /// The photo's words for the grid: the listed ones first, then the rest
  /// of the AI's pool and the old words. (When the server returns its own
  /// grid (Windows #731) its words go into [buildPhotoWordGrid] instead.)
  Widget _wordGrid(Photo photo, PhotoWordSession session, List<OldWord> old) {
    final repo = AppScope.of(context).repository;
    final words = [
      for (final w in session.words) GridWord.fromCandidate(w.candidate),
      for (final c in photo.candidates) GridWord.fromCandidate(c),
      for (final o in session.oldWords) GridWord.fromCandidate(o.candidate),
    ];
    final grid = buildPhotoWordGrid(words);
    if (grid.isEmpty) return const SizedBox.shrink();
    final listed = {for (final w in session.words) w.word.toLowerCase()};
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: PhotoWordGridTable(
        grid: grid,
        known: {
          for (final w in words)
            if (listed.contains(w.word.toLowerCase()) ||
                repo.entryByWord(w.word) != null)
              w.word.toLowerCase(),
        },
        display: (w) => _shown(w.word, w.pos),
        onWordTap: _gridTap,
      ),
    );
  }

  /// A word in the book (or on the list, saved first) opens 單字詳情; any
  /// other word can be added to the photo's list like a long-press find —
  /// pinned at its spot and saved into the word book on leaving.
  Future<void> _gridTap(GridWord g) async {
    final scope = AppScope.of(context);
    final session = _session;
    if (session == null) return;
    final onList = session.words.where((w) => w.word == g.word).firstOrNull;
    if (onList != null) return _openWord(onList);
    if (scope.repository.entryByWord(g.word) case final e?) {
      _save();
      scope.navigator.openWord(e.id);
      return;
    }
    final add = await showModalBottomSheet<bool>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text('${_shown(g.word, g.pos)}　${g.meaning}',
                  style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
              subtitle: UiText(levelLabel(g.level)),
            ),
            ListTile(
              key: const ValueKey('grid-add'),
              leading: const Icon(Icons.add_rounded, color: MColors.primary),
              title: const UiText('加入單字本'),
              onTap: () => Navigator.pop(context, true),
            ),
          ],
        ),
      ),
    );
    if (add != true || !mounted) return;
    final c = g.candidate;
    final w = c != null
        ? session.addFound(c, g.point ?? c.point)
        : session.add(
            word: g.word, meaning: g.meaning, level: g.level, at: g.point);
    if (w != null && mounted) {
      showToast(context, '已加入「${_shown(w.word, w.candidate.pos)}」');
    }
  }

  Widget _emptyState(Photo photo, PhotoWordSession session) {
    final scope = AppScope.of(context);
    final String title;
    final String body;
    Widget? action;
    switch (photo.taggingStatus) {
      case TaggingStatus.pending
          when photo.candidates.isEmpty && !scope.settings.taggingConfigured:
        title = '這台裝置沒有照片辨識';
        body = '這台裝置目前無法辨識照片，照片會先留在相片冊。';
        action = FilledButton(
          onPressed: () => scope.navigator.selectTab(AppTab.settings),
          child: const UiText('前往設定'),
        );
      case TaggingStatus.pending when photo.candidates.isEmpty:
        title = '等待 AI 辨識';
        body = 'AI 服務恢復連線後會自動處理，不用一直等在這裡。'
            '${photo.taggingError == null ? '' : '\n（${photo.taggingError}）'}';
      case TaggingStatus.tagging when photo.candidates.isEmpty:
        title = 'AI 辨識中…';
        body = '${scope.queue.progressLabel}\n可離開此頁，背景會繼續處理；請保持 App 開啟。';
      case TaggingStatus.failed:
        title = 'AI 辨識沒有成功';
        body = photo.taggingError ?? '請稍後再試。';
        action = FilledButton(
          onPressed: () => scope.queue.enqueue(photo.id),
          child: const UiText('重試'),
        );
      default:
        title = '這張照片沒有新的單字';
        body = session.oldWords.isEmpty
            ? '可以拖動難度條，或按「多看動詞」找找看其他的詞。'
            : '打開「顯示已學會單字」可以看到照片裡已經學過的詞。';
    }
    return Container(
      margin: const EdgeInsets.only(bottom: MSpace.sm),
      padding: const EdgeInsets.all(MSpace.lg),
      decoration:
          MDecor.softPanel(color: MColors.surfaceSoft, radius: MRadii.xl),
      child: Column(
        children: [
          UiText(title, style: MFont.manrope(15, FontWeight.w800, MColors.ink)),
          const SizedBox(height: MSpace.xxs + 2),
          Text(body,
              textAlign: TextAlign.center,
              style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
          if (action != null) ...[const SizedBox(height: MSpace.sm), action],
        ],
      ),
    );
  }
}

/// Under the photo while an added word waits for its spot (問題回報 #323:
/// 可在照片上點一下放位置，沒放就不標位置).
class _PlacingBar extends StatelessWidget {
  final String word;
  final VoidCallback onSkip;

  const _PlacingBar({required this.word, required this.onSkip});

  @override
  Widget build(BuildContext context) => Container(
        key: const ValueKey('placing-bar'),
        margin: const EdgeInsets.fromLTRB(20, 0, 20, 4),
        padding: const EdgeInsets.fromLTRB(14, 4, 4, 4),
        decoration:
            MDecor.softPanel(color: MColors.surfaceSoft, radius: MRadii.xl),
        child: Row(
          children: [
            const Icon(Icons.touch_app_outlined,
                size: 18, color: MColors.primary),
            const SizedBox(width: 8),
            Expanded(
              child: UiText('在照片上點一下，放「$word」的位置',
                  style: MFont.manrope(13, FontWeight.w700, MColors.ink)),
            ),
            TextButton(onPressed: onSkip, child: const UiText('不放位置')),
          ],
        ),
      );
}

/// 問題回報 #709: over the photo while its labels are hidden.
class _PinsHiddenChip extends StatelessWidget {
  const _PinsHiddenChip();

  @override
  Widget build(BuildContext context) => Positioned(
        left: 0,
        right: 0,
        bottom: 12,
        child: IgnorePointer(
          child: Center(
            child: Container(
              key: const ValueKey('pins-hidden'),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(999),
              ),
              child: UiText('標籤已收起，點照片展開',
                  style: MFont.manrope(12, FontWeight.w700, Colors.white)),
            ),
          ),
        ),
      );
}

/// The number on a long-pressed spot waiting for its word (問題回報 #690).
class _SpotNumber extends StatelessWidget {
  final int number;

  const _SpotNumber(this.number);

  @override
  Widget build(BuildContext context) => Container(
        width: 28,
        height: 28,
        alignment: Alignment.center,
        decoration: const BoxDecoration(
            color: MColors.primary, shape: BoxShape.circle),
        child: Text('$number',
            style: MFont.manrope(13, FontWeight.w800, Colors.white)),
      );
}

/// Shows [child] [frames] frames after it first appears; 0 shows it at
/// once (問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）). Only
/// this part is rebuilt when it shows, not the page around it.
class _AfterFrames extends StatefulWidget {
  final int frames;
  final Widget child;

  const _AfterFrames({super.key, required this.frames, required this.child});

  @override
  State<_AfterFrames> createState() => _AfterFramesState();
}

class _AfterFramesState extends State<_AfterFrames> {
  late bool _ready = widget.frames <= 0;

  @override
  void initState() {
    super.initState();
    if (!_ready) _wait(widget.frames);
  }

  void _wait(int frames) => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || _ready) return;
        if (frames > 1) {
          _wait(frames - 1);
          WidgetsBinding.instance.scheduleFrame();
        } else {
          setState(() => _ready = true);
        }
      });

  @override
  void didUpdateWidget(_AfterFrames old) {
    super.didUpdateWidget(old);
    if (widget.frames <= 0) _ready = true;
  }

  @override
  Widget build(BuildContext context) =>
      _ready ? widget.child : const SizedBox.shrink();
}
