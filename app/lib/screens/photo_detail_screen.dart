import '../l10n/ui_text.dart';
import '../services/learning_content.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/lexicon_pack.dart';
import '../services/photo_word_session.dart';
import '../services/word_selector.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';

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
  // Positions from the mock, relative to the scrolling content (the nav
  // bar ends at y=104; the photo sits 16px below it).
  static const _photoTop = 16.0;
  static const _dialTop = _photoTop + 274; // collapsed dial, y=394
  static const _levelTop = _photoTop + 126; // expanded control, y=246
  static const _sliderTop = _photoTop + 166; // difficulty-slider, y=286

  AppScope? _scope;
  PhotoWordSession? _session;
  bool _visible = false;

  bool _dialOpen = false;

  /// The dial was opened by a long press and follows the finger.
  bool _dialDragging = false;
  final _sliderKey = GlobalKey();

  /// An added word waiting for a tap on the photo to get its pin.
  SessionWord? _placing;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final scope = _scope = AppScope.of(context);
    _session ??= PhotoWordSession(
      repo: scope.repository,
      photoId: widget.photoId,
      queue: scope.queue,
    )..addListener(_changed);
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
              title: Text('${displayWord(w.word)}　${w.candidate.meaning}',
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
        showToast(context, '已刪除「${displayWord(w.word)}」，這張照片不會再推薦它');
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
  }

  void _placeAt(LabelPoint at) {
    final w = _placing;
    if (w == null) return;
    _session!.move(w, at);
    setState(() => _placing = null);
  }

  // ── Dial ──────────────────────────────────────────────────────────

  int? _levelAt(Offset global) {
    final box = _sliderKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return null;
    final dy = box.globalToLocal(global).dy;
    return ((dy - 12) / 40).floor().clamp(0, cefrLevels.length - 1);
  }

  void _dialTo(Offset global, {bool live = true}) {
    final i = _levelAt(global);
    if (i != null) _session!.setTarget(i, live: live);
  }

  void _closeDial({bool commit = true}) {
    if (commit) _session!.setTarget(_session!.target);
    setState(() {
      _dialOpen = false;
      _dialDragging = false;
    });
  }

  // ── Build ─────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final session = _session!;
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
        final old = session.showLearned ? session.oldWords : const <OldWord>[];
        final pins = [
          for (final w in session.words)
            if (w.placed)
              PinData(
                id: w.word,
                anchor: w.anchor,
                word: displayWord(w.word),
                zh: typedMeaning(
                    w.candidate.meaning,
                    LexiconPack.instance
                            .lookup(w.word, pos: w.candidate.pos)
                            ?.entry
                            .entryType ??
                        'word'),
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
              word: displayWord(o.word),
              zh: typedMeaning(
                  o.candidate.meaning,
                  LexiconPack.instance
                          .lookup(o.word, pos: o.candidate.pos)
                          ?.entry
                          .entryType ??
                      'word'),
              muted: true,
            ),
        ];
        SessionWord? wordOf(PinData p) =>
            session.words.where((w) => w.word == p.id).firstOrNull;

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
                      text: '照片「${photo.title}」裡的英文單字：'
                          '${session.words.map((w) => '${displayWord(w.word)} ${w.candidate.meaning}').join('、')}',
                    )),
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    child: Stack(
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Padding(
                              padding: const EdgeInsets.all(MSpace.md),
                              child: Container(
                                height: 320,
                                decoration:
                                    MDecor.heroPhotoFrame(radius: MRadii.xxl),
                                clipBehavior: Clip.antiAlias,
                                child: PinnedPhoto(
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
                                  onPhotoTap:
                                      _placing == null ? null : _placeAt,
                                  overlay: _overlayFor(photo, session),
                                  // Labels keep off the difficulty dial,
                                  // which overlaps the photo's corner.
                                  avoid: const [
                                    Rect.fromLTWH(
                                        13 - 16, _dialTop - _photoTop, 52, 58),
                                  ],
                                ),
                              ),
                            ),
                            if (_placing case final w?)
                              _PlacingBar(
                                word: displayWord(w.word),
                                onSkip: () => setState(() => _placing = null),
                              ),
                            _buildList(photo, session, old),
                          ],
                        ),
                        // Stays mounted (invisible) while a long press
                        // drives the open dial, so the gesture continues.
                        if (!_dialOpen || _dialDragging)
                          Positioned(
                            key: const ValueKey('dial'),
                            left: 13,
                            top: _dialTop,
                            child: GestureDetector(
                              onLongPressStart: (d) => setState(() {
                                _dialOpen = true;
                                _dialDragging = true;
                              }),
                              onLongPressMoveUpdate: (d) =>
                                  _dialTo(d.globalPosition),
                              onLongPressEnd: (_) => _closeDial(),
                              child: Opacity(
                                opacity: _dialOpen ? 0 : 1,
                                child: _DifficultyDial(
                                  level: session.targetLevel,
                                  onTap: () => setState(() => _dialOpen = true),
                                ),
                              ),
                            ),
                          ),
                        if (_dialOpen) ...[
                          Positioned(
                            left: 16,
                            top: _levelTop,
                            child: _LevelCircle(
                              level: session.targetLevel,
                              onTap: () => _closeDial(),
                            ),
                          ),
                          Positioned(
                            left: 16,
                            top: _sliderTop,
                            child: GestureDetector(
                              onVerticalDragUpdate: (d) =>
                                  _dialTo(d.globalPosition),
                              onVerticalDragEnd: (_) => _closeDial(),
                              child: _DifficultySlider(
                                key: _sliderKey,
                                level: session.targetLevel,
                                onSelect: (l) {
                                  session.setTarget(cefrLevels.indexOf(l));
                                  _closeDial(commit: false);
                                },
                              ),
                            ),
                          ),
                          Positioned(
                            left: 60,
                            top: _sliderTop + 12 + session.target * 40 + 2,
                            child: _DialBubble(
                              text:
                                  '${session.targetLevel} · ${relativeDifficulty(session.offset)}',
                              hint: _dialDragging ? '放開手指完成' : null,
                            ),
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

  Widget? _overlayFor(Photo photo, PhotoWordSession session) {
    final scope = AppScope.of(context);
    if (scope.queue.current == photo.id ||
        (photo.taggingStatus == TaggingStatus.tagging &&
            photo.candidates.isEmpty)) {
      return const _PhotoBadgeOverlay(icon: null, text: 'AI 辨識中…');
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

  Widget _buildList(Photo photo, PhotoWordSession session, List<OldWord> old) {
    final scope = AppScope.of(context);
    final topping = scope.queue.isToppingUp(photo.id);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
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
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const ValueKey('add-word'),
              onPressed: _addWord,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: UiText('自己加字',
                  style: MFont.manrope(13, FontWeight.w800, MColors.primary)),
            ),
          ),
          // 問題回報 #276: the "no 建立 button, leaving saves" rule used to sit
          // under all five words; say it next to the list title instead.
          Row(
            children: [
              const Icon(Icons.check_circle_outline_rounded,
                  size: 14, color: MColors.label),
              const SizedBox(width: 4),
              Expanded(
                child: UiText('返回時自動保存，不用再按建立。',
                    style: MFont.manrope(12, FontWeight.w600, MColors.label)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          _LevelRow(
            level: session.targetLevel,
            offset: session.offset,
            bias: session.bias,
            busy: topping,
            onBias: session.setBias,
            onEasier: session.target > 0
                ? () => session.setTarget(session.target - 1)
                : null,
            onHarder: session.target < cefrLevels.length - 1
                ? () => session.setTarget(session.target + 1)
                : null,
          ),
          const SizedBox(height: 12),
          if (session.words.isEmpty) _emptyState(photo, session),
          for (final w in session.words) ...[
            Dismissible(
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
                    content: UiText('已把「${displayWord(w.word)}」移到已學會'),
                    action: SnackBarAction(
                      label: ui(context, '復原'),
                      onPressed: () => session.restore(undo),
                    ),
                  ));
              },
              child: _WordCard(
                word: displayWord(w.word),
                ipa: w.candidate.ipa ??
                    scope.repository.entryByWord(w.word)?.ipa,
                zh: typedMeaning(
                    w.candidate.meaning,
                    LexiconPack.instance
                            .lookup(w.word, pos: w.candidate.pos)
                            ?.entry
                            .entryType ??
                        'word'),
                level: w.candidate.level,
                starred: w.starred,
                onTap: () => _openWord(w),
                onMore: () => _pinActions(w),
                onAudio: () => scope.speak(context, w.word,
                    language: scope.repository.language),
                onStar: () => session.toggleStar(w),
              ),
            ),
            const SizedBox(height: 12),
          ],
          if (old.isNotEmpty) ...[
            const SizedBox(height: 4),
            const SectionLabel('已學會與學習中的舊詞'),
            const SizedBox(height: 8),
            for (final o in old) ...[
              _OldWordRow(
                word: displayWord(o.word),
                zh: typedMeaning(
                    o.candidate.meaning,
                    LexiconPack.instance
                            .lookup(o.word, pos: o.candidate.pos)
                            ?.entry
                            .entryType ??
                        'word'),
                learned: o.learned,
                onRestore: o.learned
                    ? () {
                        session.restore(o);
                        showToast(context, '已復原「${displayWord(o.word)}」');
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
          if (session.selection != null && session.selection!.scored.isNotEmpty)
            Center(
              child: TextButton(
                onPressed: () =>
                    showSelectionReasons(context, session.selection!),
                child: UiText('為什麼是這些字？',
                    style: MFont.manrope(12, FontWeight.w700, MColors.primary)),
              ),
            ),
        ],
      ),
    );
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
            ? '可以用「難一點」或「更多動作」找找看其他的詞。'
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

/// The level line under the list title, with the spec's shortcuts:
/// 「更多動作」「更多描述」「簡單一點」「難一點」.

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
