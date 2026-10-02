import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../app/app_scope.dart';
import '../../theme/mobile_theme.dart';
import 'common.dart';
import 'm_icon.dart';

/// Figma bottom-tab-bar (Word Database · Mobile 54:290): 22px icons,
/// Manrope Bold 11 labels, blue when selected. The bottom padding is the
/// mock's 24px or the device's home-indicator inset, if larger. The mock
/// has four tabs; the fifth, 複習 (Flashcard), is spec section 7's, drawn
/// in the same icon style.
class MobileTabBar extends StatelessWidget {
  final AppTab current;
  final ValueChanged<AppTab> onSelect;

  const MobileTabBar(
      {super.key, required this.current, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final bottom = math.max(24.0, MediaQuery.paddingOf(context).bottom);
    Widget tab(AppTab tab, String label, MIcon icon, MIcon activeIcon) {
      final active = tab == current;
      final needsTint = active && icon == activeIcon;
      return Tap(
        onTap: () => onSelect(tab),
        label: label,
        labelOnly: true,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: active ? MColors.primarySoft : Colors.transparent,
            borderRadius: MRadii.rSm,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              MSvg(active ? activeIcon : icon,
                  size: 22, tint: needsTint ? MColors.primary : null),
              const SizedBox(height: 3),
              Text(
                label,
                style: MFont.manrope(11, FontWeight.w700,
                    active ? MColors.primary : MColors.label),
              ),
            ],
          ),
        ),
      );
    }

    return Container(
      padding: EdgeInsets.fromLTRB(16, 10, 16, bottom),
      decoration: const BoxDecoration(
        color: MColors.surface,
        border: Border(top: BorderSide(color: MColors.hairline)),
        boxShadow: MShadows.tabBar,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          tab(AppTab.camera, '拍照', MIcon.tabCamera, MIcon.tabCamera),
          tab(AppTab.album, '相片冊', MIcon.tabGallery, MIcon.tabGalleryActive),
          tab(AppTab.review, '複習', MIcon.tabCards, MIcon.tabCardsActive),
          tab(AppTab.words, '單字本', MIcon.tabBook, MIcon.tabBookActive),
          tab(AppTab.settings, '設定', MIcon.tabSettings, MIcon.tabSettings),
        ],
      ),
    );
  }
}
