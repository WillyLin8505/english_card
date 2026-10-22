import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../theme/card_style.dart';
import '../theme/mobile_theme.dart';

/// 設定 →「卡片樣式」(問題回報 #346): one tile per style with a miniature of
/// the review card drawn from that style's own [CardLook] tokens, so the
/// learner sees the difference before choosing.
class CardStylePicker extends StatelessWidget {
  final CardStyle selected;
  final ValueChanged<CardStyle> onChanged;

  const CardStylePicker({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final style in CardStyle.values)
          _StyleTile(
            style: style,
            selected: style == selected,
            onTap: () => onChanged(style),
          ),
      ],
    );
  }
}

class _StyleTile extends StatelessWidget {
  final CardStyle style;
  final bool selected;
  final VoidCallback onTap;

  const _StyleTile(
      {required this.style, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final look = CardLook.forStyle(style);
    final border =
        selected ? MColors.primary : MColors.label.withValues(alpha: 0.4);
    return Semantics(
      button: true,
      selected: selected,
      label: style.label,
      child: InkWell(
        key: ValueKey('cardStyle-${style.name}'),
        borderRadius: BorderRadius.circular(MRadii.md),
        onTap: onTap,
        child: Container(
          width: 148,
          padding: const EdgeInsets.all(6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(MRadii.md),
            border: Border.all(color: border, width: selected ? 2 : 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ExcludeSemantics(child: _Mini(look: look)),
              const SizedBox(height: 6),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (selected)
                    const Padding(
                      padding: EdgeInsets.only(right: 4),
                      child: Icon(Icons.check_circle,
                          size: 16, color: MColors.primary),
                    ),
                  Flexible(
                      child: UiText(style.label, textAlign: TextAlign.center)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Mini extends StatelessWidget {
  final CardLook look;
  const _Mini({required this.look});

  @override
  Widget build(BuildContext context) {
    final photo = Container(
      height: 28,
      decoration: BoxDecoration(
        color: MColors.label.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(look.photoRadius.clamp(0, 8)),
      ),
      child: const Icon(Icons.image_outlined, size: 16, color: Colors.white),
    );
    final word =
        Text('apple', style: look.headword.copyWith(fontSize: 16, height: 1.1));
    final meaning = Text(ui(context, '蘋果'),
        style: look.meaning.copyWith(fontSize: 12, height: 1.2));
    final panel = look.sectionPanel(0);
    final section = Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      decoration: panel,
      child: Row(children: [
        if (look.sectionIcon('例句') case final icon?)
          Padding(
            padding: const EdgeInsets.only(right: 2),
            child: Icon(icon, size: 10, color: look.sectionIconColor),
          ),
        Text(ui(context, '例句'), style: look.sectionLabel.copyWith(fontSize: 9)),
      ]),
    );
    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (look.photoHero) ...[photo, const SizedBox(height: 4)],
        word,
        meaning,
        const SizedBox(height: 4),
        section,
        if (!look.photoHero) ...[const SizedBox(height: 4), photo],
      ],
    );
    return Container(
      height: 118,
      clipBehavior: Clip.hardEdge,
      decoration: BoxDecoration(
        color: look.canvas,
        borderRadius: BorderRadius.circular(MRadii.sm),
      ),
      padding: const EdgeInsets.all(6),
      child: Container(
        decoration: look.card?.copyWith(boxShadow: const []),
        padding: const EdgeInsets.all(6),
        child: content,
      ),
    );
  }
}
