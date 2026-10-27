import '../../l10n/ui_text.dart';
import '../../models/word_entry.dart' show cefrLevels;
import '../../services/learning_content.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../theme/mobile_theme.dart';
import 'm_icon.dart';

/// Tap target with a pointer cursor and button semantics — the mock's
/// buttons are plain frames, so this is how they become interactive.
class Tap extends StatelessWidget {
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final String? label;
  final Widget child;

  /// The [label] already says everything the child shows: screen readers
  /// read the label once instead of the label and then the same text again
  /// (問題回報: 「開始使用 開始使用」).
  final bool labelOnly;

  const Tap(
      {super.key,
      this.onTap,
      this.onLongPress,
      this.label,
      this.labelOnly = false,
      required this.child});

  @override
  Widget build(BuildContext context) => Semantics(
        button: onTap != null,
        label: label == null ? null : ui(context, label!),
        excludeSemantics: labelOnly && label != null,
        child: MouseRegion(
          cursor: onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            onLongPress: onLongPress,
            child: child,
          ),
        ),
      );
}

/// Learner-facing copy for a failed camera / gallery / save step. The raw
/// exception goes to the debug log only.
String photoErrorMessage(Object error) {
  debugPrint('photo error: $error');
  final text = error.toString().toLowerCase();
  if (RegExp(r'permission|denied|access').hasMatch(text)) {
    return '沒有相機或相簿權限，請到手機設定開啟後再試。';
  }
  if (RegExp(r'enospc|no space|storage|disk full').hasMatch(text)) {
    return '手機儲存空間不足，請清出空間後再試。';
  }
  if (error is FormatException ||
      RegExp(r'decode|format|codec').hasMatch(text)) {
    return '這張照片的格式無法使用，請換一張。';
  }
  return '發生問題，請再試一次。';
}

void showToast(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: UiText(message)));
}

/// The square nav-bar buttons (back-btn / share-btn / star-btn-detail):
/// A 48px target around a 20px icon, radius 12.
class NavIconButton extends StatelessWidget {
  final Widget icon;
  final Color? background;
  final bool bordered;
  final VoidCallback? onTap;
  final String label;

  const NavIconButton({
    super.key,
    required this.icon,
    required this.label,
    this.background,
    this.bordered = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: label,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: MDecor.softPanel(
            color: background ?? MColors.surfaceSoft,
            radius: MRadii.sm,
          ).copyWith(
            border: bordered ? Border.all(color: MColors.hairline) : null,
          ),
          child: SizedBox.square(dimension: 20, child: Center(child: icon)),
        ),
      );
}

/// Back button (arrow-left on #f4f7fb).
class BackNavButton extends StatelessWidget {
  final VoidCallback? onTap;

  const BackNavButton({super.key, this.onTap});

  @override
  Widget build(BuildContext context) => NavIconButton(
        label: '返回',
        icon: const MSvg(MIcon.arrowLeft, size: 20),
        onTap: onTap ?? () => Navigator.of(context).maybePop(),
      );
}

/// Share button (share-2, white with a #e9edf7 border).
class ShareNavButton extends StatelessWidget {
  final VoidCallback? onTap;

  const ShareNavButton({super.key, this.onTap});

  @override
  Widget build(BuildContext context) => NavIconButton(
        label: '分享',
        icon: const MSvg(MIcon.share, size: 18),
        background: MColors.surface,
        bordered: true,
        onTap: onTap,
      );
}

/// The Manrope nav bar (word DB, 項目照片, 照片詳情, 單字詳情): 24px side
/// padding, 12px vertical, title in Manrope ExtraBold 18.
class MNavBar extends StatelessWidget {
  final String title;
  final Widget? leading;
  final Widget? trailing;
  final bool divider;

  /// Width of each side slot; wider when [trailing] holds two buttons.
  final double sideWidth;

  const MNavBar({
    super.key,
    required this.title,
    this.leading,
    this.trailing,
    this.divider = true,
    this.sideWidth = 48,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: MSpace.xl, vertical: MSpace.sm),
      decoration: MDecor.listTileSurface(showDivider: divider),
      child: Row(
        children: [
          SizedBox(width: sideWidth, child: leading),
          Expanded(
            child: UiText(
              title,
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: MFont.title,
            ),
          ),
          SizedBox(width: sideWidth, child: trailing),
        ],
      ),
    );
  }
}

/// The Inter top bar of 我的相片冊 / 選擇照片: 48px round buttons on
/// #f5f8fc, title in Inter Bold 18.
class AlbumTopBar extends StatelessWidget {
  final String title;
  final Widget leading;
  final Widget trailing;

  const AlbumTopBar({
    super.key,
    required this.title,
    required this.leading,
    required this.trailing,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: MSpace.md, vertical: MSpace.sm),
        child: Row(
          children: [
            leading,
            Expanded(
              child: UiText(
                title,
                textAlign: TextAlign.center,
                style: MFont.inter(18, FontWeight.w700, MColors.albumInk),
              ),
            ),
            trailing,
          ],
        ),
      );
}

class RoundIconButton extends StatelessWidget {
  final Widget icon;
  final String label;
  final VoidCallback? onTap;

  const RoundIconButton(
      {super.key, required this.icon, required this.label, this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: label,
        child: Container(
          width: 48,
          height: 48,
          decoration: MDecor.softPanel(
            color: MColors.surfaceSoft,
            radius: MRadii.pill,
          ).copyWith(
            border: Border.all(color: MColors.hairline),
          ),
          child: Center(child: icon),
        ),
      );
}

/// The Inter "Chip / …" pills of the word DB filters and photo cards:
/// 28px, radius 14, blue when [active].
class FilterPill extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback? onTap;

  const FilterPill(
      {super.key, required this.label, this.active = false, this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        child: Container(
          height: 28,
          padding: const EdgeInsets.symmetric(horizontal: MSpace.sm),
          decoration: MDecor.chipSurface(active: active, radius: MRadii.md),
          child: Center(
            widthFactor: 1,
            child: UiText(
              label,
              maxLines: 1,
              softWrap: false,
              style: MFont.inter(12, FontWeight.w600,
                  active ? MColors.primaryDeep : MColors.gray700,
                  height: 1.4),
            ),
          ),
        ),
      );
}

/// A [FilterPill] that opens a menu of options.
class MenuPill<T> extends StatelessWidget {
  final String label;
  final bool active;
  final List<(T?, String)> options;
  final T? selected;
  final ValueChanged<T?> onSelected;

  const MenuPill({
    super.key,
    required this.label,
    required this.options,
    required this.selected,
    required this.onSelected,
    this.active = false,
  });

  @override
  Widget build(BuildContext context) => PopupMenuButton<int>(
        tooltip: '',
        position: PopupMenuPosition.under,
        padding: EdgeInsets.zero,
        color: MColors.surface,
        surfaceTintColor: Colors.transparent,
        onSelected: (i) => onSelected(options[i].$1),
        itemBuilder: (_) => [
          for (final (i, (value, text)) in options.indexed)
            PopupMenuItem(
              value: i,
              height: 40,
              child: UiText(
                text,
                style: MFont.inter(
                  14,
                  value == selected ? FontWeight.w700 : FontWeight.w500,
                  value == selected ? MColors.primaryDeep : MColors.gray700,
                ),
              ),
            ),
        ],
        child: FilterPill(label: label, active: active),
      );
}

/// Word-detail tag chips (同義詞 / 拼字相近 / 詞形變化 …).
class TagChip extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final bool localize;

  const TagChip(this.label,
      {super.key, this.onTap, this.onLongPress, this.localize = true});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        onLongPress: onLongPress,
        child: Container(
          padding:
              const EdgeInsets.symmetric(horizontal: MSpace.sm, vertical: 6),
          decoration: MDecor.chipSurface(active: true, radius: MRadii.sm),
          child: Text(localize ? ui(context, label) : label,
              style: MFont.manrope(12, FontWeight.w700, MColors.primary)),
        ),
      );
}

/// 問題回報 #580 (owner decision): a related word's native meaning is often
/// a whole translated definition (dwarf「小人：…」); the relation rows show
/// only the text before the first 「；」/「：」 (or ";" ":"), at most 10
/// characters, with 「…」 when cut. The data is unchanged.
String shortRelationMeaning(String meaning) {
  final text = meaning.trim();
  final head = text.split(RegExp('[；：;:]')).first.trim();
  final first = head.isEmpty ? text : head;
  final chars = first.runes.toList();
  if (chars.length <= 10) return first;
  return '${String.fromCharCodes(chars.take(10))}…';
}

/// A relation row's chip (近義詞／相關詞…): the word and its short meaning
/// (問題回報 #580). When the meaning was cut, a long press — or a tap, when
/// the chip opens nothing else — shows the full text, and again folds it.
class RelationChip extends StatefulWidget {
  final String word;
  final String meaning;
  final VoidCallback? onTap;

  const RelationChip(this.word, {super.key, required this.meaning, this.onTap});

  @override
  State<RelationChip> createState() => _RelationChipState();
}

class _RelationChipState extends State<RelationChip> {
  bool _full = false;

  @override
  Widget build(BuildContext context) {
    final full = widget.meaning.trim();
    final short = shortRelationMeaning(full);
    final cut = short != full;
    void toggle() => setState(() => _full = !_full);
    return TagChip('${widget.word}　${_full ? full : short}'.trim(),
        localize: false,
        onTap: widget.onTap ?? (cut ? toggle : null),
        onLongPress: cut ? toggle : null);
  }
}

/// 我的相片冊 category pills.
class AlbumPill extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const AlbumPill(
      {super.key,
      required this.label,
      required this.active,
      required this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: MSpace.md, vertical: MSpace.xs),
          decoration: active
              ? MDecor.primaryPill(radius: MRadii.xl)
              : MDecor.softPanel(color: MColors.albumPill, radius: MRadii.xl),
          child: UiText(
            label,
            style: active
                ? MFont.inter(14, FontWeight.w700, Colors.white)
                : MFont.inter(14, FontWeight.w500, MColors.albumMuted),
          ),
        ),
      );
}

/// The 等級 badge (A1–C2).
class LevelBadge extends StatelessWidget {
  final String level;

  const LevelBadge(this.level, {super.key});

  @override
  Widget build(BuildContext context) => Container(
        height: 24,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration:
            MDecor.softPanel(color: MColors.primarySoft, radius: MRadii.sm),
        child: Center(
          widthFactor: 1,
          child: UiText(levelLabel(level),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: MFont.inter(11, FontWeight.w700, MColors.primaryDeep,
                  height: 1.4)),
        ),
      );
}

/// The albums' 標籤程度 picker (問題回報 #113): a default view, then A1–C2.
/// Choosing a level only filters which labels the photos show; it never
/// changes a photo's saved words or its dial setting.
class LabelLevelBar extends StatelessWidget {
  /// The selected level, or null for the default view.
  final String? level;

  /// The default view's chip ("學習中", "全部").
  final String defaultLabel;
  final ValueChanged<String?> onChanged;

  const LabelLevelBar({
    super.key,
    required this.level,
    required this.defaultLabel,
    required this.onChanged,
  });

  // Every option fits on a 320px phone without scrolling: the default
  // chip takes two shares of the row, each level one.
  @override
  Widget build(BuildContext context) => SizedBox(
        height: 28,
        child: Row(
          children: [
            UiText('程度',
                style: MFont.inter(12, FontWeight.w600, MColors.gray500)),
            const SizedBox(width: MSpace.xs),
            for (final (i, l) in [null, ...cefrLevels].indexed) ...[
              if (i > 0) const SizedBox(width: 4),
              Expanded(
                flex: l == null ? 2 : 1,
                child: MergeSemantics(
                  child: Semantics(
                    selected: l == level,
                    label: l == null ? null : '標籤程度 ${levelLabel(l)}',
                    child: Tap(
                      onTap: () => onChanged(l),
                      child: Container(
                        decoration: MDecor.chipSurface(
                            active: l == level, radius: MRadii.md),
                        alignment: Alignment.center,
                        child: UiText(
                          l ?? defaultLabel,
                          maxLines: 1,
                          softWrap: false,
                          overflow: TextOverflow.clip,
                          style: MFont.inter(
                              12,
                              FontWeight.w600,
                              l == level
                                  ? MColors.primaryDeep
                                  : MColors.gray700,
                              height: 1.4),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      );
}

/// Grey Manrope section label ("繁體中文", "實用例句" …).
class SectionLabel extends StatelessWidget {
  final String text;

  const SectionLabel(this.text, {super.key});

  @override
  Widget build(BuildContext context) => UiText(text,
      style: MFont.caption.copyWith(fontSize: 13, fontWeight: FontWeight.w700));
}

TextStyle _sdsBody(Color color) =>
    MFont.inter(16, FontWeight.w400, color, height: 1);

/// Simple Design System "Search" (Figma 36:200): white pill, icon right.
class SdsSearchField extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final String hint;

  const SdsSearchField({
    super.key,
    required this.controller,
    required this.onChanged,
    this.hint = '搜尋{L}或{N}',
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: MSpace.md),
      decoration: MDecor.card(radius: MRadii.pill, shadow: MShadows.soft),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              onChanged: onChanged,
              cursorColor: MColors.sdsText,
              style: _sdsBody(MColors.sdsText),
              decoration: InputDecoration(
                isCollapsed: true,
                contentPadding: EdgeInsets.zero,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                hintText: ui(context, hint),
                hintStyle: _sdsBody(MColors.sdsPlaceholder),
              ),
            ),
          ),
          const SizedBox(width: MSpace.xs),
          SvgPicture.asset('assets/figma/search.svg', width: 16, height: 16),
        ],
      ),
    );
  }
}

/// Simple Design System "Button", Medium (Figma 36:205). [neutral] is the
/// library's Neutral variant, used for 開始複習 next to the Primary
/// 新增單字.
class SdsButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;
  final bool neutral;

  const SdsButton(
      {super.key,
      required this.label,
      required this.onPressed,
      this.neutral = false});

  @override
  Widget build(BuildContext context) {
    final bg = neutral ? MColors.sdsNeutral : MColors.sdsBrand;
    return Tap(
      onTap: onPressed,
      label: label,
      labelOnly: true,
      child: Container(
        height: 40,
        padding: const EdgeInsets.all(MSpace.sm),
        decoration: BoxDecoration(
          color: bg,
          border: Border.all(
              color: neutral ? MColors.sdsNeutral : MColors.sdsBrand),
          borderRadius: MRadii.rXs,
        ),
        child: UiText(label,
            style: _sdsBody(neutral ? MColors.sdsText : MColors.sdsOnBrand)),
      ),
    );
  }
}

/// The blue pill button used for 顯示答案, 開始複習 and 完成. [decoration],
/// [height] and [textStyle] restyle it (顯示答案 in a 卡片樣式, #317).
class PrimaryButton extends StatelessWidget {
  final String label;
  final String? shortcut;
  final VoidCallback? onTap;
  final BoxDecoration Function(bool enabled)? decoration;
  final double height;
  final TextStyle? textStyle;

  const PrimaryButton(
      {super.key,
      required this.label,
      required this.onTap,
      this.shortcut,
      this.decoration,
      this.height = 52,
      this.textStyle});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: shortcut == null
            ? label
            : '${ui(context, label)}（${ui(context, shortcut!)}）',
        labelOnly: true,
        child: Container(
          height: height,
          alignment: Alignment.center,
          decoration: decoration?.call(onTap != null) ??
              (onTap == null
                  ? MDecor.softPanel(color: MColors.label, radius: 26)
                  : MDecor.primaryPill(radius: 26)),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Flexible(
                  child: UiText(label,
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: textStyle ??
                          MFont.manrope(16, FontWeight.w800, Colors.white))),
              if (shortcut != null) ...[
                const SizedBox(width: 10),
                UiText(shortcut!,
                    style: MFont.manrope(
                        11, FontWeight.w600, MColors.onOverlayMuted)),
              ],
            ],
          ),
        ),
      );
}
