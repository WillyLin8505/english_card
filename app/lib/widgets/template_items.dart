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
