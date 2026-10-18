part of '../screens/flashcard_screen.dart';

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
  final FlashcardSession? session;

  const FlashcardFront({super.key, required this.entry, this.session});

  @override
  Widget build(BuildContext context) {
    final s = session;
    if (s != null && s.exercise != null) {
      return _InteractiveExercise(session: s, entry: entry);
    }
    final layout = s?.repo.template.publishedLayout;
    if (layout != null) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (final section in layout['sections'] as List)
          if (section['side'] == 'front' && section['visible'] == true)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: _Block(
                    section['key'] == 'hint' ? '字首提示' : '母語提示',
                    Text(
                        section['key'] == 'hint'
                            ? firstLetterHint(entry.word)
                            : entry.meaning,
                        textAlign: TextAlign.center,
                        style: MFont.manrope(
                            24, FontWeight.w800, MColors.primary)),
                    collapsed: section['collapsed'] == true)),
      ]);
    }
    return Column(
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
        UiText(
          '先在心裡想出這個字，再按「顯示答案」。',
          textAlign: TextAlign.center,
          style: MFont.manrope(13, FontWeight.w600, MColors.label),
        ),
      ],
    );
  }
}
