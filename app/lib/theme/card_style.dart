import 'package:flutter/material.dart';

import 'mobile_theme.dart';

/// 設定 →「卡片樣式」(問題回報 #317): how the review card looks. There is one
/// set of card widgets; a style only changes the tokens they read, never
/// what the card shows or how a review runs.
enum CardStyle {
  /// The look before #317.
  classic,

  /// A — 簡潔留白: one white card, large type, hairline-separated sections.
  minimal,

  /// B — 圖片沉浸: the photo leads, the word sits on it; sections are tiles.
  /// The default (owner's choice on 問題回報 #317).
  immersive,

  /// C — 活潑遊戲: a sticker-like card with tinted, icon-labelled sections.
  playful;

  static const CardStyle fallback = CardStyle.immersive;

  static CardStyle parse(String? name) => CardStyle.values
      .firstWhere((s) => s.name == name, orElse: () => fallback);

  String get label => switch (this) {
        CardStyle.classic => '經典',
        // No A/B/C: those were the mock-up codes (問題回報 #521).
        CardStyle.minimal => '簡潔留白',
        CardStyle.immersive => '圖片沉浸',
        CardStyle.playful => '活潑遊戲',
      };
}

/// The tokens one [CardStyle] gives the card front and back. Sizes keep to
/// the 4/8 pt grid; text colours pass WCAG AA on the surface they sit on.
class CardLook {
  final CardStyle style;

  /// The review screen behind the card.
  final Color canvas;

  /// The card around the front and the back; null: content on the canvas.
  final BoxDecoration? card;
  final EdgeInsets cardPadding;

  /// Space between the back's sections, and between a title and its body.
  final double sectionGap;
  final double labelGap;

  /// What sits behind back section [i] (null: nothing) and its padding.
  final BoxDecoration? Function(int i) sectionPanel;
  final EdgeInsets sectionPadding;

  final TextStyle headword;
  final TextStyle ipa;
  final TextStyle meaning;
  final TextStyle sectionLabel;

  /// An icon before a section title, or null.
  final IconData? Function(String label) sectionIcon;
  final Color sectionIconColor;

  final BoxDecoration Function(bool linked) chip;
  final EdgeInsets chipPadding;
  final double chipMinHeight;
  final TextStyle chipWord;
  final TextStyle chipMeaning;

  final BoxDecoration example;
  final EdgeInsets examplePadding;
  final double exampleGap;

  final double photoHeight;
  final double photoRadius;

  /// Back: the photo goes first, with the word written over it.
  final bool photoHero;

  final double frontPhotoHeight;
  final double frontPhotoRadius;
  final TextStyle frontHint;
  final TextStyle frontMeaning;
  final TextStyle exerciseTitle;

  /// Outlined buttons on the card (hints, answer options) take this colour
  /// and corner; null keeps the app's buttons.
  final Color? buttonAccent;
  final double buttonRadius;

  /// The bar fixed under the card: 顯示答案 on the front, the four grades on
  /// the back. A grade tile keeps its spec colours (bg, fg); a style only
  /// changes its shape.
  final BoxDecoration dock;
  final BoxDecoration Function(bool enabled) answerButton;
  final double answerHeight;
  final TextStyle answerText;
  final BoxDecoration Function(Color bg, Color fg) ratingTile;
  final double ratingHeight;
  final double ratingLabelSize;

  const CardLook._({
    required this.style,
    required this.canvas,
    required this.card,
    required this.cardPadding,
    required this.sectionGap,
    required this.labelGap,
    required this.sectionPanel,
    required this.sectionPadding,
    required this.headword,
    required this.ipa,
    required this.meaning,
    required this.sectionLabel,
    required this.sectionIcon,
    required this.sectionIconColor,
    required this.chip,
    required this.chipPadding,
    required this.chipMinHeight,
    required this.chipWord,
    required this.chipMeaning,
    required this.example,
    required this.examplePadding,
    required this.exampleGap,
    required this.photoHeight,
    required this.photoRadius,
    required this.photoHero,
    required this.frontPhotoHeight,
    required this.frontPhotoRadius,
    required this.frontHint,
    required this.frontMeaning,
    required this.exerciseTitle,
    this.buttonAccent,
    this.buttonRadius = MRadii.md,
    required this.dock,
    required this.answerButton,
    required this.answerHeight,
    required this.answerText,
    required this.ratingTile,
    required this.ratingHeight,
    required this.ratingLabelSize,
  });

  static BoxDecoration? _noPanel(int _) => null;
  static IconData? _noIcon(String _) => null;

  static CardLook of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<CardLookScope>()?.look ??
      forStyle(CardStyle.classic);

  static final _cache = <CardStyle, CardLook>{};

  static CardLook forStyle(CardStyle style) =>
      _cache[style] ??= switch (style) {
        CardStyle.classic => _classic(),
        CardStyle.minimal => _minimal(),
        CardStyle.immersive => _immersive(),
        CardStyle.playful => _playful(),
      };

  /// Exactly the card as it was before #317.
  static CardLook _classic() => CardLook._(
        style: CardStyle.classic,
        canvas: MColors.canvas,
        card: null,
        cardPadding: EdgeInsets.zero,
        sectionGap: 16,
        labelGap: 6,
        sectionPanel: _noPanel,
        sectionPadding: EdgeInsets.zero,
        headword: MFont.manrope(32, FontWeight.w800, MColors.ink),
        ipa: MFont.manrope(16, FontWeight.w600, MColors.muted),
        meaning: MFont.manrope(22, FontWeight.w800, MColors.primary),
        sectionLabel:
            MFont.caption.copyWith(fontSize: 13, fontWeight: FontWeight.w700),
        sectionIcon: _noIcon,
        sectionIconColor: MColors.label,
        chip: (_) => MDecor.chipSurface(active: true, radius: MRadii.sm),
        chipPadding:
            const EdgeInsets.symmetric(horizontal: MSpace.sm, vertical: 6),
        chipMinHeight: 0,
        chipWord: MFont.manrope(13, FontWeight.w800, MColors.primary),
        chipMeaning: MFont.manrope(12, FontWeight.w600, MColors.muted),
        example: MDecor.softPanel(color: MColors.surfaceSoft, radius: MRadii.md),
        examplePadding: const EdgeInsets.symmetric(
            horizontal: MSpace.sm, vertical: MSpace.xs),
        exampleGap: MSpace.xxs,
        photoHeight: 200,
        photoRadius: 16,
        photoHero: false,
        frontPhotoHeight: 260,
        frontPhotoRadius: 18,
        frontHint: MFont.manrope(30, FontWeight.w800, MColors.ink),
        frontMeaning: MFont.manrope(24, FontWeight.w800, MColors.primary),
        exerciseTitle: MFont.manrope(20, FontWeight.w800, MColors.ink),
        dock: const BoxDecoration(
          color: MColors.surface,
          border: Border(top: BorderSide(color: MColors.hairline)),
          boxShadow: MShadows.tabBar,
        ),
        answerButton: (enabled) => enabled
            ? MDecor.primaryPill(radius: 26)
            : MDecor.softPanel(color: MColors.label, radius: 26),
        answerHeight: 52,
        answerText: MFont.manrope(16, FontWeight.w800, Colors.white),
        ratingTile: (bg, fg) => BoxDecoration(
          color: bg,
          borderRadius: MRadii.rMd,
          border: Border.all(color: fg.withValues(alpha: 0.12)),
        ),
        ratingHeight: 72,
        ratingLabelSize: 14,
      );

  // A: quiet type hierarchy (40 / 20 / 15 / 12), ink instead of blue for the
  // meaning, outline chips, generous 24–32 pt spacing; low density.
  static const _aInk = Color(0xFF111827); // 17.7:1 on white
  static const _aMuted = Color(0xFF4B5563); // 7.6:1 on white
  static const _aAccent = Color(0xFF1D4ED8); // 6.7:1 on white

  static CardLook _minimal() => CardLook._(
        style: CardStyle.minimal,
        canvas: const Color(0xFFF3F4F6),
        card: BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(28),
          boxShadow: MShadows.elevated,
        ),
        cardPadding: const EdgeInsets.fromLTRB(24, 32, 24, 32),
        sectionGap: 24,
        labelGap: 8,
        sectionPanel: (i) => const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xFFE5E7EB)))),
        sectionPadding: const EdgeInsets.only(top: 24),
        headword: MFont.manrope(40, FontWeight.w700, _aInk, height: 1.15),
        ipa: MFont.manrope(15, FontWeight.w500, _aMuted),
        meaning: MFont.manrope(20, FontWeight.w700, _aInk),
        sectionLabel: MFont.manrope(12, FontWeight.w700, _aMuted)
            .copyWith(letterSpacing: 1.2),
        sectionIcon: _noIcon,
        sectionIconColor: _aMuted,
        chip: (_) => BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(MRadii.xs),
          border: Border.all(color: const Color(0xFFD1D5DB)),
        ),
        chipPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        chipMinHeight: 44,
        chipWord: MFont.manrope(14, FontWeight.w700, _aAccent),
        chipMeaning: MFont.manrope(13, FontWeight.w500, _aMuted),
        example: const BoxDecoration(
            border: Border(left: BorderSide(color: _aAccent, width: 3))),
        examplePadding: const EdgeInsets.fromLTRB(12, 4, 0, 4),
        exampleGap: 12,
        photoHeight: 220,
        photoRadius: 12,
        photoHero: false,
        frontPhotoHeight: 260,
        frontPhotoRadius: 12,
        frontHint: MFont.manrope(36, FontWeight.w700, _aInk)
            .copyWith(letterSpacing: 2),
        frontMeaning: MFont.manrope(22, FontWeight.w700, _aInk),
        exerciseTitle: MFont.manrope(20, FontWeight.w700, _aInk),
        buttonAccent: _aInk,
        buttonRadius: MRadii.xs,
        // A flat white bar, an ink button (17.7:1) and outlined grades.
        dock: const BoxDecoration(
          color: MColors.surface,
          border: Border(top: BorderSide(color: Color(0xFFE5E7EB))),
        ),
        answerButton: (enabled) => BoxDecoration(
          color: enabled ? _aInk : const Color(0xFF9CA3AF),
          borderRadius: BorderRadius.circular(12),
        ),
        answerHeight: 52,
        answerText: MFont.manrope(16, FontWeight.w700, Colors.white)
            .copyWith(letterSpacing: 0.5),
        ratingTile: (bg, fg) => BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: fg, width: 1.5),
        ),
        ratingHeight: 64,
        ratingLabelSize: 14,
      );

  // B: the photo is the hero (300 pt, word on a dark scrim); the rest are
  // white tiles on a cool grey canvas, so photo and text never compete.
  static const _bInk = Color(0xFF0F172A); // 17.9:1 on white
  static const _bMuted = Color(0xFF475569); // 7.6:1 on white
  static const _bAccent = Color(0xFF0369A1); // 5.9:1 on white

  static CardLook _immersive() => CardLook._(
        style: CardStyle.immersive,
        canvas: const Color(0xFFE8ECF2),
        card: null,
        cardPadding: EdgeInsets.zero,
        sectionGap: 12,
        labelGap: 8,
        sectionPanel: (i) => BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(20),
          boxShadow: MShadows.soft,
        ),
        sectionPadding: const EdgeInsets.all(16),
        headword: MFont.manrope(36, FontWeight.w800, Colors.white, height: 1.1),
        ipa: MFont.manrope(15, FontWeight.w600, _bMuted),
        meaning: MFont.manrope(22, FontWeight.w800, _bInk),
        sectionLabel: MFont.manrope(13, FontWeight.w800, _bMuted),
        sectionIcon: _noIcon,
        sectionIconColor: _bMuted,
        chip: (_) => BoxDecoration(
          color: const Color(0xFFF1F5F9),
          borderRadius: BorderRadius.circular(MRadii.sm),
        ),
        chipPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        chipMinHeight: 44,
        chipWord: MFont.manrope(14, FontWeight.w800, _bAccent),
        chipMeaning: MFont.manrope(13, FontWeight.w600, _bMuted),
        example: MDecor.softPanel(color: const Color(0xFFF1F5F9), radius: 12),
        examplePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        exampleGap: 8,
        photoHeight: 320,
        photoRadius: 24,
        photoHero: true,
        frontPhotoHeight: 420,
        frontPhotoRadius: 24,
        frontHint: MFont.manrope(32, FontWeight.w800, _bInk),
        frontMeaning: MFont.manrope(24, FontWeight.w800, _bAccent),
        exerciseTitle: MFont.manrope(22, FontWeight.w800, _bInk),
        buttonAccent: _bAccent,
        buttonRadius: MRadii.pill,
        // A raised sheet with rounded top corners, a deep-sky pill (white
        // text 5.9:1) and soft filled grade tiles.
        dock: const BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          boxShadow: MShadows.tabBar,
        ),
        answerButton: (enabled) => BoxDecoration(
          color: enabled ? _bAccent : MColors.label,
          borderRadius: BorderRadius.circular(28),
          boxShadow: enabled ? MShadows.soft : null,
        ),
        answerHeight: 56,
        answerText: MFont.manrope(17, FontWeight.w800, Colors.white),
        ratingTile: (bg, fg) => BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
        ),
        ratingHeight: 72,
        ratingLabelSize: 15,
      );

  // C: a sticker card (2 pt ink outline, hard offset shadow), sections on
  // rotating pastel tints with an icon each, pill chips; denser and louder.
  static const _cInk = Color(0xFF1F1147); // 17.4:1 on white
  static const _cMuted = Color(0xFF52496B); // 8.3:1 on white, ≥ 7:1 on tints
  static const _cAccent = Color(0xFF6D28D9); // 7.1:1 on white
  static const _cTints = [
    Color(0xFFEDE9FE),
    Color(0xFFDCFCE7),
    Color(0xFFFFEDD5),
    Color(0xFFE0F2FE),
  ];

  static IconData? _playfulIcon(String label) => switch (label) {
        '詞性與意思' || '逐義釋義' => Icons.translate_rounded,
        '例句與翻譯' => Icons.chat_bubble_outline_rounded,
        '詞形變化' => Icons.auto_fix_high_rounded,
        '同義詞' => Icons.favorite_border_rounded,
        '反義詞' => Icons.swap_horiz_rounded,
        '相關詞' => Icons.hub_outlined,
        '近音字' => Icons.hearing_rounded,
        '容易混淆的字' => Icons.psychology_alt_outlined,
        '構詞拆解' => Icons.extension_outlined,
        _ => Icons.star_border_rounded,
      };

  static CardLook _playful() => CardLook._(
        style: CardStyle.playful,
        canvas: const Color(0xFFFFF4E0),
        card: BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: _cInk, width: 2),
          boxShadow: const [
            BoxShadow(color: _cInk, offset: Offset(0, 6), blurRadius: 0)
          ],
        ),
        cardPadding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
        sectionGap: 12,
        labelGap: 8,
        sectionPanel: (i) => BoxDecoration(
          color: _cTints[i % _cTints.length],
          borderRadius: BorderRadius.circular(20),
        ),
        sectionPadding: const EdgeInsets.all(12),
        headword: MFont.manrope(36, FontWeight.w800, _cInk, height: 1.1),
        ipa: MFont.manrope(15, FontWeight.w700, _cMuted),
        meaning: MFont.manrope(24, FontWeight.w800, _cAccent),
        sectionLabel: MFont.manrope(14, FontWeight.w800, _cInk),
        sectionIcon: _playfulIcon,
        sectionIconColor: _cAccent,
        chip: (_) => BoxDecoration(
          color: MColors.surface,
          borderRadius: BorderRadius.circular(MRadii.pill),
          border: Border.all(color: _cInk.withValues(alpha: 0.25), width: 1.5),
        ),
        chipPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        chipMinHeight: 44,
        chipWord: MFont.manrope(14, FontWeight.w800, _cAccent),
        chipMeaning: MFont.manrope(13, FontWeight.w700, _cMuted),
        example: MDecor.softPanel(color: MColors.surface, radius: 16),
        examplePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        exampleGap: 8,
        photoHeight: 220,
        photoRadius: 20,
        photoHero: false,
        frontPhotoHeight: 260,
        frontPhotoRadius: 20,
        frontHint: MFont.manrope(36, FontWeight.w800, _cAccent)
            .copyWith(letterSpacing: 2),
        frontMeaning: MFont.manrope(24, FontWeight.w800, _cInk),
        exerciseTitle: MFont.manrope(26, FontWeight.w800, _cInk),
        buttonAccent: _cAccent,
        buttonRadius: MRadii.pill,
        // Stickers again: 2 pt ink outlines with a hard offset shadow.
        dock: const BoxDecoration(
          color: Color(0xFFFFF4E0),
          border: Border(top: BorderSide(color: _cInk, width: 2)),
        ),
        answerButton: (enabled) => BoxDecoration(
          color: enabled ? _cAccent : MColors.label,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: _cInk, width: 2),
          boxShadow: enabled
              ? const [
                  BoxShadow(color: _cInk, offset: Offset(0, 4), blurRadius: 0)
                ]
              : null,
        ),
        answerHeight: 56,
        answerText: MFont.manrope(18, FontWeight.w800, Colors.white),
        ratingTile: (bg, fg) => BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _cInk, width: 2),
          boxShadow: const [
            BoxShadow(color: _cInk, offset: Offset(0, 4), blurRadius: 0)
          ],
        ),
        ratingHeight: 72,
        ratingLabelSize: 15,
      );
}

/// Gives the card widgets below it a [CardLook].
class CardLookScope extends InheritedWidget {
  final CardLook look;

  const CardLookScope({super.key, required this.look, required super.child});

  @override
  bool updateShouldNotify(CardLookScope oldWidget) => look != oldWidget.look;
}
