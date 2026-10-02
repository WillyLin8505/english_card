import '../services/learning_content.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
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

/// The dial's wording next to the CEFR level (spec section 3: 輪盤中心
/// 同時顯示文字與 CEFR 範圍，避免只靠顏色判斷).
String relativeDifficulty(int offset) => switch (offset) {
      <= -2 => '很簡單',
      -1 => '簡單',
      0 => '符合程度',
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
/// correct it. There is no 建立 button — leaving the page saves the list
/// and creates the cards.
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
              subtitle: const Text('可查看意思、修改名稱或標為已學會。'),
            ),
            ListTile(
              leading: const Icon(Icons.menu_book_outlined),
              title: const Text('查看單字'),
              onTap: () => Navigator.pop(context, 'open'),
            ),
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('修改標籤'),
              onTap: () => Navigator.pop(context, 'edit'),
            ),
            ListTile(
              leading: const Icon(Icons.check_circle_outline,
                  color: MColors.success),
              title: const Text('我已經會了（移到已學會）'),
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
        );
        if (result != null) {
          final level = lexicon.resolve(result.word, w.candidate.pos).level;
          session.correct(w,
              word: result.word, meaning: result.zh, level: level);
        }
      case 'known':
        session.swipe(w);
    }
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
                        padding: const EdgeInsets.all(32),
                        child: Text(
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
            PinData(
              id: w.word,
              anchor: w.anchor,
              word: displayWord(w.word),
              zh: w.candidate.meaning,
              linked: w.candidate.inDatabase || LexiconPack.instance.isEmpty,
            ),
          for (final o in old)
            PinData(
              id: 'old:${o.word}',
              anchor: o.anchor,
              word: displayWord(o.word),
              zh: o.candidate.meaning,
              muted: true,
            ),
        ];
        SessionWord? wordOf(PinData p) =>
            session.words.where((w) => w.word == p.id).firstOrNull;

        return Scaffold(
          backgroundColor: Colors.white,
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
                              padding: const EdgeInsets.all(16),
                              child: Container(
                                height: 320,
                                decoration: MDecor.heroPhotoFrame(radius: MRadii.xxl),
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
              icon: Icons.link_off_rounded, text: '尚未設定 AI 辨識服務');
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
                child: Text('辨識單字列表 (${session.words.length})',
                    style: MFont.manrope(15, FontWeight.w800, MColors.muted)),
              ),
              Text('顯示已學會單字',
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
                session.swipe(w);
                showToast(context, '已把「${displayWord(w.word)}」移到已學會');
              },
              child: _WordCard(
                word: displayWord(w.word),
                ipa: w.candidate.ipa ??
                    scope.repository.entryByWord(w.word)?.ipa,
                zh: w.candidate.meaning,
                level: w.candidate.level,
                starred: w.starred,
                onTap: () => _openWord(w),
                onMore: () => _pinActions(w),
                onAudio: () => scope.speaker
                    .say(w.word, language: scope.repository.language),
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
                zh: o.candidate.meaning,
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
          Text(
            '左滑單字表示已經會了；拖曳照片上的標籤可調整位置。\n離開這一頁時會自動保存。',
            textAlign: TextAlign.center,
            style: MFont.manrope(12, FontWeight.w600, MColors.label),
          ),
          if (session.selection != null && session.selection!.scored.isNotEmpty)
            Center(
              child: TextButton(
                onPressed: () =>
                    showSelectionReasons(context, session.selection!),
                child: Text('為什麼是這些字？',
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
        title = '尚未設定 AI 辨識服務';
        body = '填好服務網址與 API Key 後，這張照片會自動開始辨識。';
        action = FilledButton(
          onPressed: () => scope.navigator.selectTab(AppTab.settings),
          child: const Text('前往設定'),
        );
      case TaggingStatus.pending when photo.candidates.isEmpty:
        title = '等待 AI 辨識';
        body = 'AI 服務恢復連線後會自動處理，不用一直等在這裡。'
            '${photo.taggingError == null ? '' : '\n（${photo.taggingError}）'}';
      case TaggingStatus.tagging when photo.candidates.isEmpty:
        title = 'AI 辨識中…';
        body = '大約需要半分鐘。';
      case TaggingStatus.failed:
        title = 'AI 辨識沒有成功';
        body = photo.taggingError ?? '請稍後再試。';
        action = FilledButton(
          onPressed: () => scope.queue.enqueue(photo.id),
          child: const Text('重試'),
        );
      default:
        title = '這張照片沒有新的單字';
        body = session.oldWords.isEmpty
            ? '可以用「難一點」或「更多動作」找找看其他的詞。'
            : '打開「顯示已學會單字」可以看到照片裡已經學過的詞。';
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: MColors.surfaceSoft,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Text(title, style: MFont.manrope(15, FontWeight.w800, MColors.ink)),
          const SizedBox(height: 6),
          Text(body,
              textAlign: TextAlign.center,
              style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
          if (action != null) ...[const SizedBox(height: 12), action],
        ],
      ),
    );
  }
}

/// The level line under the list title, with the spec's shortcuts:
/// 「更多動作」「更多描述」「簡單一點」「難一點」.
class _LevelRow extends StatelessWidget {
  final String level;
  final int offset;
  final PosBias bias;
  final bool busy;
  final ValueChanged<PosBias> onBias;
  final VoidCallback? onEasier;
  final VoidCallback? onHarder;

  const _LevelRow({
    required this.level,
    required this.offset,
    required this.bias,
    required this.busy,
    required this.onBias,
    required this.onEasier,
    required this.onHarder,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('單字難度 ${levelLabel(level)} · ${relativeDifficulty(offset)}',
                  style: MFont.manrope(13, FontWeight.w700, MColors.dialBlue)),
              if (busy) ...[
                const SizedBox(width: 8),
                const SizedBox.square(
                    dimension: 12,
                    child: CircularProgressIndicator(strokeWidth: 1.6)),
                const SizedBox(width: 4),
                Text('補充候選詞…',
                    style: MFont.manrope(12, FontWeight.w600, MColors.label)),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilterPill(
                label: '多看動詞',
                active: bias == PosBias.actions,
                onTap: () => onBias(PosBias.actions),
              ),
              FilterPill(
                label: '多看形容詞',
                active: bias == PosBias.descriptions,
                onTap: () => onBias(PosBias.descriptions),
              ),
              FilterPill(label: '簡單一點', onTap: onEasier),
              FilterPill(label: '難一點', onTap: onHarder),
            ],
          ),
        ],
      );
}

class _KnownBackground extends StatelessWidget {
  const _KnownBackground();

  @override
  Widget build(BuildContext context) => Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        decoration: BoxDecoration(
          color: MColors.success,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_rounded, color: Colors.white, size: 20),
            const SizedBox(width: 6),
            Text('已學會',
                style: MFont.manrope(15, FontWeight.w800, Colors.white)),
          ],
        ),
      );
}

/// Figma word-card-Coffee (24:59).
class _WordCard extends StatelessWidget {
  final String word;
  final String? ipa;
  final String zh;
  final String level;
  final bool starred;
  final VoidCallback onTap;
  final VoidCallback onAudio;
  final VoidCallback onStar;
  final VoidCallback onMore;

  const _WordCard({
    required this.word,
    required this.ipa,
    required this.zh,
    required this.level,
    required this.starred,
    required this.onTap,
    required this.onAudio,
    required this.onStar,
    required this.onMore,
  });

  @override
  Widget build(BuildContext context) {
    Widget action(Color bg, Widget icon, String label, VoidCallback onTap) =>
        Tap(
          onTap: onTap,
          label: label,
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
                color: bg, borderRadius: BorderRadius.circular(12)),
            child: SizedBox.square(dimension: 18, child: Center(child: icon)),
          ),
        );

    return Tap(
      onTap: onTap,
      label: '$word $zh',
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: MColors.borderSoft),
          borderRadius: BorderRadius.circular(20),
          boxShadow: const [
            BoxShadow(
                color: Color.fromRGBO(110, 122, 138, 0.05),
                offset: Offset(0, 4),
                blurRadius: 8),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Flexible(
                        child: Text(word,
                            overflow: TextOverflow.ellipsis,
                            style: MFont.manrope(
                                18, FontWeight.w800, MColors.ink)),
                      ),
                      if (ipa != null) ...[
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(ipa!,
                              overflow: TextOverflow.ellipsis,
                              style: MFont.manrope(
                                  13, FontWeight.w500, MColors.label)),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      if (zh.isNotEmpty)
                        Flexible(
                          child: Text(zh,
                              overflow: TextOverflow.ellipsis,
                              style: MFont.manrope(
                                  15, FontWeight.w700, MColors.primary)),
                        ),
                      const SizedBox(width: 8),
                      Text(levelLabel(level),
                          style: MFont.manrope(
                              11, FontWeight.w800, MColors.label)),
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
                tooltip: '管理這個單字',
                onPressed: onMore,
                icon: const Icon(Icons.more_horiz)),
            action(MColors.primarySoft,
                const MSvg(MIcon.audioWaveform, size: 18), '播放發音', onAudio),
            const SizedBox(width: 10),
            action(
              starred ? MColors.successSoft : MColors.surfaceSoft,
              MSvg(starred ? MIcon.star : MIcon.starOff, size: 18),
              starred ? '取消鎖定' : '鎖定（調整難度時保留）',
              onStar,
            ),
          ],
        ),
      ),
    );
  }
}

/// A hidden word shown with 「顯示已學會單字」: 已學會 ones have a small
/// 復原 button (spec: 每個封存詞旁提供小型復原按鈕).
class _OldWordRow extends StatelessWidget {
  final String word;
  final String zh;
  final bool learned;
  final VoidCallback? onRestore;

  const _OldWordRow({
    required this.word,
    required this.zh,
    required this.learned,
    required this.onRestore,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: MColors.surfaceSoft,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(
                      text: word,
                      style: MFont.manrope(15, FontWeight.w800, MColors.muted)),
                  TextSpan(
                      text: '  $zh',
                      style: MFont.manrope(13, FontWeight.w600, MColors.label)),
                ]),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Text(learned ? '已學會' : '學習中',
                style: MFont.manrope(12, FontWeight.w700,
                    learned ? MColors.success : MColors.primary)),
            if (onRestore != null) ...[
              const SizedBox(width: 8),
              Tap(
                onTap: onRestore,
                label: '復原 $word',
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: MColors.borderSoft),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text('復原',
                      style:
                          MFont.manrope(12, FontWeight.w800, MColors.primary)),
                ),
              ),
            ],
          ],
        ),
      );
}

class _PhotoBadgeOverlay extends StatelessWidget {
  final IconData? icon;
  final String text;

  const _PhotoBadgeOverlay({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) => ColoredBox(
        color: const Color(0x66000000),
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: const Color.fromRGBO(28, 36, 52, 0.85),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon == null)
                  const SizedBox.square(
                    dimension: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  )
                else
                  Icon(icon, size: 16, color: Colors.white),
                const SizedBox(width: 8),
                Text(text,
                    style: MFont.manrope(13, FontWeight.w700, Colors.white)),
              ],
            ),
          ),
        ),
      );
}

const _dialShadow = [
  BoxShadow(
      color: Color.fromRGBO(20, 28, 46, 0.18),
      offset: Offset(0, 4),
      blurRadius: 6),
];

/// Figma "Difficulty Dial / Collapsed" (48:73): gauge, needle, level.
/// Long-press to open it and drag to a level (like a camera's ISO dial);
/// a tap opens it until a level is chosen.
class _DifficultyDial extends StatelessWidget {
  final String level;
  final VoidCallback onTap;

  const _DifficultyDial({required this.level, required this.onTap});

  @override
  Widget build(BuildContext context) {
    // The mock shows B1 with the needle at 40°; other levels step 40°.
    final angle =
        (-40 + cefrLevels.indexOf(level) * 40) * 3.141592653589793 / 180;
    return Tap(
      onTap: onTap,
      label: '單字難度 ${levelLabel(level)}，點一下或長按調整',
      child: Container(
        width: 52,
        height: 58,
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: MColors.gray200),
          borderRadius: BorderRadius.circular(26),
          boxShadow: const [
            BoxShadow(
                color: Color.fromRGBO(20, 28, 46, 0.18),
                offset: Offset(0, 4),
                blurRadius: 12),
          ],
        ),
        child: Stack(
          children: [
            // Gauge: a 30px box at (10, 6) whose arc starts 20.57% in.
            const Positioned(
              left: 10 + 30 * 0.2057,
              top: 6,
              child:
                  MSvg.sized(MIcon.difficultyGauge, width: 23.8275, height: 30),
            ),
            // Needle: 10px, rotated about its centre; its 40° bounding box
            // sits at (15, 21) in the mock, so its centre is (18.83, 24.21).
            Positioned(
              left: 18.83 - 5,
              top: 24.21 - 1,
              child: Transform.rotate(
                angle: angle,
                child:
                    const MSvg.sized(MIcon.gaugeNeedle, width: 10, height: 2),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              top: 43.5 - 6.5,
              child: Text(
                level,
                textAlign: TextAlign.center,
                style: MFont.inter(10, FontWeight.w600, MColors.dialBlue),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Figma difficulty-control-expanded (54:229).
class _LevelCircle extends StatelessWidget {
  final String level;
  final VoidCallback onTap;

  const _LevelCircle({required this.level, required this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: '收起難度選單',
        child: Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: MColors.gray200),
            borderRadius: BorderRadius.circular(18),
            boxShadow: _dialShadow,
          ),
          child: Center(
            child: Text(levelLabel(level),
                style: MFont.manrope(12, FontWeight.w800, MColors.dialBlue)),
          ),
        ),
      );
}

/// Figma difficulty-slider (54:231): A1–C2, the current one highlighted.
class _DifficultySlider extends StatelessWidget {
  final String level;
  final ValueChanged<String> onSelect;

  const _DifficultySlider(
      {super.key, required this.level, required this.onSelect});

  @override
  Widget build(BuildContext context) => Container(
        width: 36,
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: MColors.gray200),
          borderRadius: BorderRadius.circular(18),
          boxShadow: _dialShadow,
        ),
        child: Column(
          children: [
            for (final (i, l) in cefrLevels.indexed) ...[
              if (i > 0) const SizedBox(height: 8),
              Tap(
                onTap: () => onSelect(l),
                label: '難度 $l',
                child: Container(
                  height: 32,
                  decoration: l == level
                      ? BoxDecoration(
                          color: MColors.primarySoft,
                          borderRadius: BorderRadius.circular(16),
                        )
                      : null,
                  child: Center(
                    child: Text(
                      l,
                      style: l == level
                          ? MFont.manrope(12, FontWeight.w800, MColors.dialBlue)
                          : MFont.manrope(12, FontWeight.w700, MColors.label),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      );
}

/// The label beside the open dial: level and wording.
class _DialBubble extends StatelessWidget {
  final String text;
  final String? hint;

  const _DialBubble({required this.text, this.hint});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: const Color.fromRGBO(28, 36, 52, 0.85),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(text, style: MFont.manrope(12, FontWeight.w800, Colors.white)),
            if (hint != null)
              Text(hint!,
                  style: MFont.manrope(
                      10, FontWeight.w600, const Color(0xCCFFFFFF))),
          ],
        ),
      );
}
