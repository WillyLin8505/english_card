import '../services/learning_content.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app/app_scope.dart';
import '../models/card_template.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/flashcard_session.dart';
import '../services/fsrs_scheduler.dart';
import '../services/word_database_repository.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';

/// "b _ _ _ _ _ _" — the front's hint: the answer's first letter, one
/// underscore per remaining letter; a phrase keeps its words and spaces
/// (spec section 4: 片語保留單字與空格結構).
String firstLetterHint(String answer) {
  final letter = RegExp(r'\p{L}', unicode: true);
  var shown = false;
  final words = <String>[];
  for (final word in answer.trim().split(RegExp(r'\s+'))) {
    final parts = <String>[];
    for (final ch in word.split('')) {
      if (!letter.hasMatch(ch)) {
        parts.add(ch);
      } else if (shown) {
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

/// The 複習 tab — spec section 7's Flashcard entry and section 4's 主動
/// 小測驗. One continuous run: recall from the front (no photo, no typing),
/// 顯示答案, then Again / Hard / Good / Easy. Only the grade updates FSRS.
/// There is no card count, due count or score anywhere (spec section 1:
/// 不做連勝、欠卡壓力或罪惡感設計); the run stops when no card is up.
///
/// Keyboard: Space / Enter shows the answer, 1–4 grade.
class FlashcardScreen extends StatefulWidget {
  const FlashcardScreen({super.key});

  @override
  State<FlashcardScreen> createState() => _FlashcardScreenState();
}

class _FlashcardScreenState extends State<FlashcardScreen> {
  FlashcardSession? _session;
  WordDatabaseRepository? _repo;
  bool _wasBack = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final repo = AppScope.of(context).repository;
    if (repo != _repo) {
      // Another learning language: start over.
      _repo = repo;
      _end();
    }
  }

  @override
  void dispose() {
    _session?.dispose();
    super.dispose();
  }

  void _start() {
    final scope = AppScope.of(context);
    // A message from another tab (資料庫「已加入…」) would sit on the
    // grade buttons (問題回報 #97).
    ScaffoldMessenger.maybeOf(context)?.removeCurrentSnackBar();
    setState(() {
      _session = FlashcardSession(scope.repository)..addListener(_changed);
      _wasBack = false;
    });
  }

  void _end() {
    _session?.removeListener(_changed);
    _session?.dispose();
    _session = null;
    if (mounted) setState(() {});
  }

  void _changed() {
    final s = _session;
    if (s == null || !mounted) return;
    // 翻到背面時自動播放單字發音.
    if (s.showingBack && !_wasBack) {
      ScaffoldMessenger.maybeOf(context)?.removeCurrentSnackBar();
      final scope = AppScope.of(context);
      final e =
          s.card == null ? null : scope.repository.entry(s.card!.wordEntryId);
      if (e != null) {
        scope.speaker.say(e.word,
            language: scope.repository.language, audioUrl: e.audioUrl);
      }
    }
    _wasBack = s.showingBack;
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
    return Focus(
      autofocus: true,
      onKeyEvent: _onKey,
      child: Scaffold(
        backgroundColor: MColors.canvas,
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              MNavBar(
                title: '複習',
                leading: s == null
                    ? BackNavButton(
                        onTap: () => scope.navigator.selectTab(AppTab.camera))
                    : NavIconButton(
                        label: '結束複習',
                        icon: const MSvg(MIcon.xCircle, size: 20),
                        onTap: _end,
                      ),
              ),
              Expanded(
                child: s == null
                    ? _Intro(onStart: _start)
                    : s.finished
                        ? _Finished(reviewed: s.reviewed, onDone: _end)
                        : _CardView(session: s),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Intro extends StatelessWidget {
  final VoidCallback onStart;

  const _Intro({required this.onStart});

  @override
  Widget build(BuildContext context) {
    final repo = AppScope.of(context).repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final any = repo.eligibleCards().isNotEmpty;
        final waiting = repo.hasCardsWaitingForMeaning;
        return Padding(
          padding: const EdgeInsets.all(24),
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
                    border: Border.all(color: MColors.primary.withValues(alpha: 0.12))),
                child:
                    const Center(child: MSvg(MIcon.tabCardsActive, size: 40)),
              ),
              const SizedBox(height: 20),
              Text(
                  any
                      ? '想複習的時候就開始吧'
                      : waiting
                          ? '等待詞庫補齊'
                          : '現在沒有需要複習的卡片',
                  style: MFont.manrope(20, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 8),
              Text(
                // No due count (spec: 不顯示欠卡數).
                any
                    ? '先想答案，再翻面；隨時可以結束。'
                    : waiting
                        ? '單字的中文意思補齊後，會自動加入複習。'
                        : '在照片詳情挑幾個單字，或從資料庫加入單字，就會變成卡片。',
                textAlign: TextAlign.center,
                style: MFont.manrope(14, FontWeight.w600, MColors.muted),
              ),
              const SizedBox(height: 28),
              if (any) PrimaryButton(label: '開始複習', onTap: onStart),
            ],
          ),
        );
      },
    );
  }
}

/// Deliberately no totals or streaks (spec: 測驗結束畫面 is deferred).
class _Finished extends StatelessWidget {
  final int reviewed;
  final VoidCallback onDone;

  const _Finished({required this.reviewed, required this.onDone});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('今天先到這裡',
                style: MFont.manrope(22, FontWeight.w800, MColors.ink)),
            const SizedBox(height: 8),
            Text(
              '目前沒有其他需要複習的卡片了。\n下次出現的時間已經排好，想複習時再回來就好。',
              textAlign: TextAlign.center,
              style: MFont.manrope(14, FontWeight.w600, MColors.muted),
            ),
            const SizedBox(height: 28),
            PrimaryButton(label: '完成', onTap: onDone),
          ],
        ),
      );
}

class _CardView extends StatelessWidget {
  final FlashcardSession session;

  const _CardView({required this.session});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final card = session.card!;
    final entry = repo.entry(card.wordEntryId);
    if (entry == null) return const SizedBox.shrink();
    final native = scope.settings.nativeLanguage;
    final bottom = MediaQuery.paddingOf(context).bottom;
    return Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              child: session.showingBack
                  ? FlashcardBack(
                      key: ValueKey('back:${card.id}'),
                      entry: entry,
                      card: card,
                      photo: session.photo,
                      anchor: session.anchor,
                      template: repo.template,
                      learnerLevel: repo.profile.cefr,
                      onPlay: () => scope.speaker.say(entry.word,
                          language: repo.language, audioUrl: entry.audioUrl),
                      onOpen: () => scope.navigator.openWord(entry.id),
                    )
                  : FlashcardFront(
                      key: ValueKey('front:${card.id}'), entry: entry),
            ),
          ),
        ),
        // Fixed at the bottom (spec: 畫面底部固定「顯示答案」／四個評分按鈕).
        Container(
          padding: EdgeInsets.fromLTRB(20, 12, 20, 16 + bottom),
          decoration: const BoxDecoration(
            color: MColors.surface,
            border: Border(top: BorderSide(color: MColors.hairline)),
            boxShadow: MShadows.tabBar,
          ),
          child: session.showingBack
              ? RatingBar(
                  previews: repo.previewReview(card.id),
                  native: native,
                  onRate: session.rate,
                )
              : PrimaryButton(
                  label: '顯示答案', shortcut: '空白鍵', onTap: session.showAnswer),
        ),
      ],
    );
  }
}

/// A back-of-card section. Longer sections (spec section 5: 較長的相關字、
/// 詞源與來源區塊可預設收合) start [collapsed]; tapping the title opens them.
class _Block extends StatefulWidget {
  final String label;
  final Widget child;
  final bool collapsed;

  const _Block(this.label, this.child, {this.collapsed = false});

  @override
  State<_Block> createState() => _BlockState();
}

class _BlockState extends State<_Block> {
  late bool _open = !widget.collapsed;

  @override
  Widget build(BuildContext context) {
    if (!widget.collapsed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(widget.label),
          const SizedBox(height: 6),
          widget.child
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Tap(
          label: '${_open ? '收合' : '展開'}${widget.label}',
          onTap: () => setState(() => _open = !_open),
          child: Row(
            children: [
              Expanded(
                  child: ExcludeSemantics(child: SectionLabel(widget.label))),
              Icon(_open ? Icons.expand_less : Icons.expand_more,
                  size: 20, color: MColors.label),
            ],
          ),
        ),
        if (_open) ...[const SizedBox(height: 6), widget.child],
      ],
    );
  }
}

/// Front (spec section 7): no picture and nothing to type — the first
/// letter with an underscore per letter, the part of speech and the
/// native-language meaning; recall in your head.
class FlashcardFront extends StatelessWidget {
  final WordEntry entry;

  const FlashcardFront({super.key, required this.entry});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 32),
          Text(
            firstLetterHint(entry.word),
            textAlign: TextAlign.center,
            style: MFont.manrope(30, FontWeight.w800, MColors.ink),
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [if (entry.pos.isNotEmpty) TagChip(posLabel(entry.pos))],
          ),
          const SizedBox(height: 12),
          if (entry.meaning.isNotEmpty)
            Text(
              entry.meaning,
              textAlign: TextAlign.center,
              style: MFont.manrope(24, FontWeight.w800, MColors.primary),
            ),
          const SizedBox(height: 32),
          Text(
            '先在心裡想出這個字，再按「顯示答案」。',
            textAlign: TextAlign.center,
            style: MFont.manrope(13, FontWeight.w600, MColors.label),
          ),
        ],
      );
}

/// Back (spec sections 4 and 7): the answer, its pronunciation (played on
/// flip), meaning, one of the word's photos, 3–5 examples, then the
/// card template's other fields in its order; empty fields are left out.
/// 所有資訊 opens the full word.
class FlashcardBack extends StatelessWidget {
  final WordEntry entry;
  final LearningCard card;
  final Photo? photo;
  final LabelPoint? anchor;
  final CardTemplate template;
  final String learnerLevel;
  final VoidCallback onPlay;
  final VoidCallback onOpen;

  const FlashcardBack({
    super.key,
    required this.entry,
    required this.card,
    required this.photo,
    required this.anchor,
    required this.template,
    required this.learnerLevel,
    required this.onPlay,
    required this.onOpen,
  });

  Widget _chips(List<String> words) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [for (final w in words) TagChip(displayWord(w))],
      );

  Widget? _field(CardBackField field) {
    switch (field) {
      case CardBackField.word:
      case CardBackField.pronunciation:
        return null; // in the header
      case CardBackField.posAndMeaning:
        return _Block(
          '中文意思',
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (entry.pos.isNotEmpty) ...[
                    TagChip(posLabel(entry.pos)),
                    const SizedBox(width: 8)
                  ],
                  if (entry.level != null) TagChip(levelLabel(entry.level!)),
                ],
              ),
              const SizedBox(height: 6),
              Text(entry.meaning,
                  style: MFont.manrope(22, FontWeight.w800, MColors.primary)),
              if (entry.definition != null)
                Text(entry.definition!,
                    style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
            ],
          ),
        );
      case CardBackField.photoContext:
        final p = photo;
        if (p == null) return null;
        return _Block(
          '照片情境',
          SizedBox(
            height: 200,
            child: PinnedPhoto(
              photo: p,
              radius: 16,
              // Only this word's label (其他英文標籤全部隱藏).
              pins: [
                if (anchor != null)
                  PinData(
                      id: entry.id,
                      anchor: anchor!,
                      word: displayWord(entry.word),
                      zh: entry.meaning),
              ],
            ),
          ),
        );
      case CardBackField.example:
        // Spec sections 4 and 7: 3–5 examples at the learner's level.
        final recommended = learningExamples(entry, learnerLevel);
        if (recommended.isEmpty) return null;
        return _Block(
          '例句與翻譯',
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final x in recommended)
                Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: MColors.surfaceSoft,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: ExampleText(example: x),
                ),
            ],
          ),
        );
      case CardBackField.formsAndDerivations:
        final forms = {for (final f in entry.forms) f.form.toLowerCase()};
        final words = [
          for (final f in entry.forms) '${f.form}（${f.label}）',
          for (final r
              in learningRelations(entry, learnerLevel, 'derived_terms'))
            if (!forms.contains(r.word.toLowerCase())) '${r.word} ${r.meaning}',
        ];
        return words.isEmpty
            ? null
            : _Block('詞形與衍生', _chips(words), collapsed: true);
      case CardBackField.related:
        // Every related word with its native meaning (spec section 08).
        final words = {
          for (final kind in const [
            'synonyms',
            'related',
            'homophones',
            'near_homophones',
            'similar_spelling'
          ])
            for (final r in learningRelations(entry, learnerLevel, kind))
              // Sound and spelling look-alikes say so: bottle's 「battle」
              // is not a word of related meaning.
              '${r.word} ${r.meaning}${switch (kind) {
                'homophones' => '（同音）',
                'near_homophones' => '（音近）',
                'similar_spelling' => '（拼字像）',
                _ => '',
              }}',
        }.toList();
        return words.isEmpty
            ? null
            : _Block('相關字', _chips(words), collapsed: true);
      case CardBackField.morphology:
        final parts = learningMorphology(entry);
        final origin = learningEtymology(entry);
        return parts == null && origin == null
            ? null
            : _Block(
                '構詞與詞源',
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (parts != null)
                      Text(parts,
                          style:
                              MFont.manrope(15, FontWeight.w600, MColors.ink)),
                    if (parts != null && origin != null)
                      const SizedBox(height: 6),
                    if (origin != null)
                      Text(origin,
                          style: MFont.manrope(
                              13, FontWeight.w600, MColors.muted)),
                  ],
                ),
                collapsed: true);
      case CardBackField.source:
        final sources = {
          if (entry.levelSource == 'cefr-j') 'CEFR-J 詞表',
          if (entry.ipaSource == 'cmudict') 'CMUdict',
          for (final x in entry.examples)
            if (x.source != null) x.source!,
        };
        return sources.isEmpty
            ? null
            : _Block(
                '來源',
                Text(sources.join('、'),
                    style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
                collapsed: true);
      case CardBackField.learningInfo:
        final f = card.fsrs;
        final text = f.state == FsrsCardState.newCard
            ? '第一次學這張卡'
            : '穩定度 ${f.stability.toStringAsFixed(1)} 天 · 已複習 ${f.reps} 次 · 忘記 ${f.lapses} 次';
        return _Block(
            '學習資訊',
            Text(text,
                style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
            collapsed: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    // 發音與 IPA sits in the header; switched off in 卡片背面順序, the IPA
    // and the play button go (the switch used to do nothing).
    final showPronunciation = template.backFields
        .where((f) => f.field == CardBackField.pronunciation)
        .every((f) => f.visible);
    // Every visible template field that has data (spec: 可用時一併顯示；
    // 欄位沒有內容時自動省略).
    final fields = [
      for (final f in template.backFields)
        if (f.visible) _field(f.field),
    ].whereType<Widget>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(displayWord(entry.word),
                      style: MFont.manrope(32, FontWeight.w800, MColors.ink)),
                  if (entry.ipa != null && showPronunciation)
                    Text(entry.ipa!,
                        style:
                            MFont.manrope(16, FontWeight.w600, MColors.muted)),
                ],
              ),
            ),
            if (showPronunciation)
              Tap(
                label: '播放發音',
                onTap: onPlay,
                child: Container(
                  width: 48,
                  height: 48,
                  decoration: const BoxDecoration(
                      color: MColors.primary, shape: BoxShape.circle),
                  child: const Center(
                      child: MSvg(MIcon.audioWaveformWhite, size: 20)),
                ),
              ),
          ],
        ),
        for (final w in fields) ...[const SizedBox(height: 16), w],
        const SizedBox(height: 12),
        Center(
          child: TextButton(
            onPressed: onOpen,
            child: Text('查看完整單字',
                style: MFont.manrope(14, FontWeight.w800, MColors.primary)),
          ),
        ),
      ],
    );
  }
}

/// An example sentence with its translation; an AI-written translation is
/// marked 「AI 翻譯」 (spec section 7).
class ExampleText extends StatelessWidget {
  final WordExample example;

  const ExampleText({super.key, required this.example});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(example.text,
              style: MFont.manrope(15, FontWeight.w800, MColors.ink)),
          if (example.translation != null) ...[
            const SizedBox(height: 2),
            Text.rich(TextSpan(children: [
              TextSpan(
                  text: example.translation,
                  style: MFont.manrope(13, FontWeight.w700, MColors.muted)),
              if (example.aiTranslated)
                TextSpan(
                    text: '  AI 翻譯',
                    style: MFont.manrope(11, FontWeight.w800, MColors.label)),
            ])),
          ],
        ],
      );
}

/// The four grades with each one's next interval, in spec section 4's
/// colours, labelled in the native language. Keys 1–4 also work.
class RatingBar extends StatelessWidget {
  final Map<Rating, SchedulingResult> previews;
  final String native;
  final ValueChanged<Rating> onRate;

  const RatingBar(
      {super.key,
      required this.previews,
      required this.onRate,
      this.native = 'zh-TW'});

  static ({Color bg, Color fg}) colors(Rating r) => switch (r) {
        Rating.again => (bg: MColors.againBg, fg: MColors.againFg),
        Rating.hard => (bg: MColors.hardBg, fg: MColors.hardFg),
        Rating.good => (bg: MColors.goodBg, fg: MColors.goodFg),
        Rating.easy => (bg: MColors.easyBg, fg: MColors.easyFg),
      };

  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final r in Rating.values) ...[
            if (r != Rating.again) const SizedBox(width: 8),
            Expanded(
              child: Tap(
                onTap: () => onRate(r),
                // The grade and when the card comes back, read once.
                label:
                    '${r.labelIn(native)}，${r == Rating.again ? '稍後再出現' : '${intervalLabel(previews[r]!.scheduledDays)}後複習'}',
                labelOnly: true,
                child: Container(
                  height: 72,
                  decoration: BoxDecoration(
                    color: colors(r).bg,
                    borderRadius: MRadii.rMd,
                    border: Border.all(
                      color: colors(r).fg.withValues(alpha: 0.12),
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(r.labelIn(native),
                          style:
                              MFont.manrope(14, FontWeight.w800, colors(r).fg)),
                      const SizedBox(height: 2),
                      // An Again card comes back later in this same run.
                      Text(
                          r == Rating.again
                              ? '稍後再出現'
                              : '${intervalLabel(previews[r]!.scheduledDays)}後複習',
                          style: MFont.manrope(11, FontWeight.w600,
                              colors(r).fg.withValues(alpha: 0.75))),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      );
}
