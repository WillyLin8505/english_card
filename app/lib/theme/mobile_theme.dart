import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Cohesive visual tokens for the photo-English learning app.
/// Warm, clean learning feel; photos stay the hero; chrome is soft and quiet.
abstract final class MColors {
  // Core brand & ink
  static const ink = Color(0xFF1C2434);
  static const muted = Color(0xFF6E7A8A);
  static const label = Color(0xFF64748B);
  static const primary = Color(0xFF4A90D9);
  static const primaryDeep = Color(0xFF3A7BC8);
  static const primarySoft = Color(0xFFEEF4FC);
  static const primaryGlow = Color(0x264A90D9); // 15% primary

  /// Soft learning-app canvas (slightly cooler than pure white).
  static const canvas = Color(0xFFF7F9FC);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceSoft = Color(0xFFF4F7FB);
  static const borderSoft = Color(0xFFE9EDF7);
  static const border = Color(0xFFE1E6F0);
  static const hairline = Color(0xFFE5E9F2);

  static const success = Color(0xFF28C76F);
  static const successSoft = Color(0xFFECFAF1);
  static const dialBlue = Color(0xFF2F80ED);

  // Neutral scale (Inter / table screens)
  static const gray900 = Color(0xFF111827);
  static const gray700 = Color(0xFF374151);
  static const gray500 = Color(0xFF6B7280);
  static const gray200 = Color(0xFFE5E7EB);
  static const gray100 = Color(0xFFF3F4F6);
  static const gray50 = Color(0xFFF9FAFB);
  static const slate50 = Color(0xFFF8FAFC);
  static const blue100 = Color(0xFFDBEAFE);
  static const blue300 = Color(0xFF93C5FD);
  static const blue800 = Color(0xFF1E40AF);

  // Album aliases (unified tokens)
  static const albumInk = ink;
  static const albumMuted = muted;
  static const albumPill = Color(0xFFEBF3FA);
  static const albumButtonBg = surfaceSoft;
  static const albumBorder = border;

  // Simple Design System (Search / Button)
  static const sdsBorder = Color(0xFFD9D9D9);
  static const sdsPlaceholder = Color(0xFFB3B3B3);
  static const sdsText = Color(0xFF1E1E1E);
  static const sdsBrand = Color(0xFF2C2C2C);
  static const sdsOnBrand = Color(0xFFF5F5F5);
  static const sdsNeutral = Color(0xFFE3E3E3);

  /// Quiz grade colours (.again / .hard / .good / .easy).
  static const againBg = Color(0xFFFDE7E5), againFg = Color(0xFFA43C34);
  static const hardBg = Color(0xFFFFF0D6), hardFg = Color(0xFF8D5A06);
  static const goodBg = Color(0xFFE2F2EA), goodFg = Color(0xFF276548);
  static const easyBg = Color(0xFFE1EFF8), easyFg = Color(0xFF256284);

  /// Overlay helpers for photo gradients / frosted chips.
  static const photoScrim = Color(0x99000000);
  static const photoScrimLight = Color(0x66000000);
  static const frost = Color(0x33FFFFFF);
  /// Dark frosted chip on photos (ink @ ~85%).
  static const overlayChip = Color(0xD91C2434);
  /// Muted label on dark overlay chips.
  static const onOverlayMuted = Color(0xCCFFFFFF);
}

/// Consistent corner radii across chrome, cards, and pills.
abstract final class MRadii {
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 14;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double pill = 999;

  static BorderRadius of(double r) => BorderRadius.circular(r);
  static final BorderRadius rXs = BorderRadius.circular(xs);
  static final BorderRadius rSm = BorderRadius.circular(sm);
  static final BorderRadius rMd = BorderRadius.circular(md);
  static final BorderRadius rLg = BorderRadius.circular(lg);
  static final BorderRadius rXl = BorderRadius.circular(xl);
  static final BorderRadius rXxl = BorderRadius.circular(xxl);
  static final BorderRadius rPill = BorderRadius.circular(pill);
}

/// Soft elevation: quiet shadows so photos stay the hero.
abstract final class MShadows {
  static const List<BoxShadow> none = [];

  static const Color _inkShadow = Color(0x0A1C2434);
  static const Color _inkShadowDark = Color(0x141C2434);
  static const Color _inkShadowDeep = Color(0x331C2434);

  static const List<BoxShadow> soft = [
    BoxShadow(
      color: _inkShadow,
      offset: Offset(0, 2),
      blurRadius: 8,
    ),
  ];

  static const List<BoxShadow> card = [
    BoxShadow(
      color: Color(0x0F1C2434),
      offset: Offset(0, 4),
      blurRadius: 14,
      spreadRadius: -2,
    ),
    BoxShadow(
      color: Color(0x081C2434),
      offset: Offset(0, 1),
      blurRadius: 3,
    ),
  ];

  static const List<BoxShadow> elevated = [
    BoxShadow(
      color: _inkShadowDark,
      offset: Offset(0, 8),
      blurRadius: 24,
      spreadRadius: -4,
    ),
    BoxShadow(
      color: _inkShadow,
      offset: Offset(0, 2),
      blurRadius: 6,
    ),
  ];

  static const List<BoxShadow> primaryGlow = [
    BoxShadow(
      color: MColors.primaryGlow,
      offset: Offset(0, 6),
      blurRadius: 16,
      spreadRadius: -2,
    ),
  ];

  static const List<BoxShadow> pin = [
    BoxShadow(
      color: _inkShadowDark,
      offset: Offset(0, 3),
      blurRadius: 8,
    ),
  ];

  static const List<BoxShadow> pinLifted = [
    BoxShadow(
      color: _inkShadowDeep,
      offset: Offset(0, 6),
      blurRadius: 16,
    ),
  ];

  static const List<BoxShadow> tabBar = [
    BoxShadow(
      color: _inkShadow,
      offset: Offset(0, -2),
      blurRadius: 10,
    ),
  ];
}

/// Spacing scale (multiples of 4).
abstract final class MSpace {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;
}

/// Shared card / chrome decorations built from tokens.
abstract final class MDecor {
  static BoxDecoration card({
    Color color = MColors.surface,
    Color borderColor = MColors.hairline,
    double radius = MRadii.lg,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: borderColor),
        boxShadow: shadow ?? MShadows.card,
      );

  static BoxDecoration softCard({
    Color color = MColors.surface,
    double radius = MRadii.md,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.soft,
      );

  static BoxDecoration elevatedCard({
    Color color = MColors.surface,
    double radius = MRadii.lg,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.elevated,
      );

  static BoxDecoration insetCard({
    Color color = MColors.primarySoft,
    double radius = MRadii.lg,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.none,
      );

  static BoxDecoration emptyStateCard({
    Color color = MColors.surfaceSoft,
    Color borderColor = MColors.borderSoft,
    double radius = MRadii.lg,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: borderColor),
      );

  static BoxDecoration listTileSurface({
    Color color = MColors.surface,
    bool showDivider = false,
    double radius = MRadii.sm,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.soft,
        border: showDivider
            ? const Border(bottom: BorderSide(color: MColors.hairline))
            : null,
      );

  static BoxDecoration heroPhotoFrame({
    Color color = MColors.surface,
    double radius = MRadii.xxl,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.elevated,
      );

  static BoxDecoration sectionHeaderBar({
    Color color = MColors.primarySoft,
  }) =>
      BoxDecoration(
        color: color,
      );

  static BoxDecoration chipSurface({
    bool active = false,
    double radius = MRadii.pill,
    Color? color,
    Color? borderColor,
  }) =>
      BoxDecoration(
        color: color ?? (active ? MColors.primarySoft : MColors.surface),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: borderColor ??
              (active ? MColors.primary.withValues(alpha: 0.2) : MColors.hairline),
        ),
      );

  static BoxDecoration softPanel({
    Color color = MColors.surfaceSoft,
    double radius = MRadii.md,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
      );

  static BoxDecoration primaryPill({double radius = 26}) => BoxDecoration(
        color: MColors.primary,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: MShadows.primaryGlow,
      );

  /// White chrome for floating dials / compact controls.
  static BoxDecoration dialSurface({
    double radius = 18,
    List<BoxShadow>? shadow,
  }) =>
      BoxDecoration(
        color: MColors.surface,
        border: Border.all(color: MColors.gray200),
        borderRadius: BorderRadius.circular(radius),
        boxShadow: shadow ?? MShadows.soft,
      );

  /// Dark frosted pill for badges drawn over photos.
  static BoxDecoration overlayPill({
    Color color = MColors.overlayChip,
    double radius = MRadii.xl,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
      );

  /// Compact icon action well (audio / star / etc.).
  static BoxDecoration iconWell({
    required Color color,
    double radius = MRadii.sm,
  }) =>
      BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
      );
}

/// Typography. Manrope (UI) + Inter (album/meta); CJK via fallbacks.
abstract final class MFont {
  /// Tests turn this off (test/flutter_test_config.dart) so no test ever
  /// tries to download a font.
  static bool useGoogleFonts = true;

  static const _cjkFallback = <String>[
    'Noto Sans TC',
    'PingFang TC',
    'Microsoft JhengHei',
  ];

  static TextStyle _font(
    String family,
    TextStyle Function(TextStyle) google,
    double size,
    FontWeight weight,
    Color color,
    double? height,
  ) {
    final base = TextStyle(
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height,
      leadingDistribution: TextLeadingDistribution.even,
    );
    final styled =
        useGoogleFonts ? google(base) : base.copyWith(fontFamily: family);
    return styled.copyWith(fontFamilyFallback: [family, ..._cjkFallback]);
  }

  /// Manrope; Figma leading-normal means [height] stays null.
  static TextStyle manrope(double size, FontWeight weight, Color color,
          {double? height}) =>
      _font('Manrope', (s) => GoogleFonts.manrope(textStyle: s), size, weight,
          color, height);

  static TextStyle inter(double size, FontWeight weight, Color color,
          {double? height}) =>
      _font('Inter', (s) => GoogleFonts.inter(textStyle: s), size, weight,
          color, height);

  // Named scale (presentation shortcuts)
  static TextStyle get display => manrope(24, FontWeight.w800, MColors.ink);
  static TextStyle get title => manrope(18, FontWeight.w800, MColors.ink);
  static TextStyle get titleSm => manrope(16, FontWeight.w800, MColors.ink);
  static TextStyle get body => manrope(14, FontWeight.w600, MColors.ink);
  static TextStyle get bodyMuted => manrope(14, FontWeight.w600, MColors.muted);
  static TextStyle get caption => manrope(12, FontWeight.w600, MColors.label);
  static TextStyle get overline => manrope(11, FontWeight.w700, MColors.label);
}

abstract final class MobileTheme {
  static ThemeData light() {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: MColors.primary,
        primary: MColors.primary,
        surface: MColors.surface,
        onSurface: MColors.ink,
      ),
      scaffoldBackgroundColor: MColors.canvas,
    );
    return base.copyWith(
      textTheme: base.textTheme.apply(
        fontFamily:
            MFont.useGoogleFonts ? GoogleFonts.manrope().fontFamily : 'Manrope',
        fontFamilyFallback: const [
          'Noto Sans TC',
          'PingFang TC',
          'Microsoft JhengHei'
        ],
        bodyColor: MColors.ink,
        displayColor: MColors.ink,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: MColors.surface,
        foregroundColor: MColors.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: true,
      ),
      cardTheme: CardThemeData(
        color: MColors.surface,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: MRadii.rLg,
          side: const BorderSide(color: MColors.hairline),
        ),
        margin: EdgeInsets.zero,
      ),
      dividerTheme: const DividerThemeData(
        color: MColors.hairline,
        thickness: 1,
        space: 1,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: MColors.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: MRadii.rXl),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: MColors.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(MRadii.xl)),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: MColors.ink,
        contentTextStyle: MFont.manrope(14, FontWeight.w600, Colors.white),
        shape: RoundedRectangleBorder(borderRadius: MRadii.rSm),
      ),
      inputDecorationTheme: InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: MColors.surface,
        border: OutlineInputBorder(
          borderRadius: MRadii.rSm,
          borderSide: const BorderSide(color: MColors.gray200),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: MRadii.rSm,
          borderSide: const BorderSide(color: MColors.gray200),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: MRadii.rSm,
          borderSide: const BorderSide(color: MColors.primary, width: 1.5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: MColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          shadowColor: MColors.primaryGlow,
          shape: RoundedRectangleBorder(borderRadius: MRadii.rXxl),
          textStyle: MFont.manrope(16, FontWeight.w800, Colors.white),
        ),
      ),
    );
  }
}

