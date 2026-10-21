import 'package:flutter/material.dart';
import '../models/card_template.dart';

/// Applies published item counts, retaining an explicit expand-all control.
class TemplateItems extends StatefulWidget {
  final TemplateField settings;
  final List<Widget> children;
  const TemplateItems(
      {super.key, required this.settings, required this.children});
  @override
  State<TemplateItems> createState() => _TemplateItemsState();
}

class _TemplateItemsState extends State<TemplateItems> {
  bool expanded = false;
  @override
  Widget build(BuildContext context) {
    final limit = widget.settings.limit ?? widget.children.length;
    final overflow = widget.children.length > limit;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ...(expanded ? widget.children : widget.children.take(limit)),
      if (overflow && widget.settings.expandAll)
        TextButton(
            onPressed: () => setState(() => expanded = !expanded),
            child: Text(expanded ? '收合項目' : '顯示全部')),
    ]);
  }
}

/// Shows the first [initial] children, the rest behind 顯示更多 / 收起.
/// [wrap] lays the children out as flowing chips instead of a column.
class ShowMoreItems extends StatefulWidget {
  final int initial;
  final List<Widget> children;
  final bool wrap;
  const ShowMoreItems(
      {super.key,
      required this.initial,
      required this.children,
      this.wrap = false});
  @override
  State<ShowMoreItems> createState() => _ShowMoreItemsState();
}

class _ShowMoreItemsState extends State<ShowMoreItems> {
  bool open = false;
  @override
  Widget build(BuildContext context) {
    final hidden = widget.children.length - widget.initial;
    final shown = open || hidden <= 0
        ? widget.children
        : widget.children.take(widget.initial).toList();
    final toggle = hidden > 0
        ? TextButton(
            onPressed: () => setState(() => open = !open),
            child: Text(open ? '收起' : '顯示更多（$hidden）'))
        : null;
    if (widget.wrap) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 8, children: shown),
        if (toggle != null) toggle,
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ...shown,
      if (toggle != null) toggle,
    ]);
  }
}
