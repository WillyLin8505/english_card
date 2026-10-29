import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/ui_text.dart';
import '../../services/bulk_add_words.dart';
import '../../services/lexicon_pack.dart';
import '../../services/word_database_repository.dart';
import '../../theme/mobile_theme.dart';

/// 一次加入多個 (card #745). Returns (added, skipped), or null if cancelled.
Future<({int added, int skipped})?> showBulkAddDialog(
        BuildContext context, WordDatabaseRepository repository,
        {LexiconPack? pack}) =>
    showDialog<({int added, int skipped})>(
        context: context,
        builder: (_) =>
            _BulkAddDialog(repository, pack ?? LexiconPack.instance));

class _BulkAddDialog extends StatefulWidget {
  final WordDatabaseRepository repository;
  final LexiconPack pack;
  const _BulkAddDialog(this.repository, this.pack);

  @override
  State<_BulkAddDialog> createState() => _BulkAddDialogState();
}

class _BulkAddDialogState extends State<_BulkAddDialog> {
  final _text = TextEditingController();
  List<BulkItem>? _items;
  int _over = 0;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final t = data?.text;
    if (t == null || t.isEmpty) return;
    final cur = _text.text;
    _text.text = cur.isEmpty ? t : '$cur\n$t';
  }

  void _check() {
    final r = checkBulkWords(_text.text, widget.repository, widget.pack);
    setState(() {
      _items = r.items;
      _over = r.overLimit;
    });
  }

  void _set(int i, BulkItem item) => setState(() => _items![i] = item);

  void _take(int i, String suggestion) =>
      _set(i, classifyBulkWord(suggestion, widget.repository, widget.pack));

  void _confirm() =>
      Navigator.of(context).pop(addBulkItems(widget.repository, _items!));

  @override
  Widget build(BuildContext context) {
    final items = _items;
    final n = items?.where((i) => i.willAdd).length ?? 0;
    return AlertDialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 8),
      title: UiText('一次加入多個',
          style: MFont.manrope(18, FontWeight.w800, MColors.ink)),
      content: SizedBox(
        width: double.maxFinite,
        child: items == null ? _input() : _preview(context, items),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const UiText('取消')),
        if (items == null)
          FilledButton(
              key: const ValueKey('bulk-check'),
              onPressed: _check,
              child: const UiText('檢查'))
        else ...[
          TextButton(
              onPressed: () => setState(() => _items = null),
              child: const UiText('返回修改')),
          FilledButton(
              key: const ValueKey('bulk-confirm'),
              onPressed: n == 0 ? null : _confirm,
              child: UiText('加入 $n 個')),
        ],
      ],
    );
  }

  // Mac M332: on a 402pt phone with the keyboard up the box overflowed, so
  // the input scrolls and the box is shorter.
  Widget _input() => SingleChildScrollView(
          child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          UiText('一行一個字，也可用逗號、頓號或 Tab 分隔（一次最多 3000 個）。',
              style: MFont.inter(12, FontWeight.w400, MColors.gray500)),
          const SizedBox(height: 8),
          TextField(
            key: const ValueKey('bulk-text'),
            controller: _text,
            autofocus: true,
            minLines: 5,
            maxLines: 10,
            keyboardType: TextInputType.multiline,
            decoration: const InputDecoration(
                hintText: 'balcony\nbrewed\npick up',
                border: OutlineInputBorder()),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
                onPressed: _paste,
                icon: const Icon(Icons.content_paste_rounded, size: 16),
                label: const UiText('貼上')),
          ),
        ],
      ));

  // Up to 3000 rows (owner 10/29), so rows are built lazily in a fixed height.
  Widget _preview(BuildContext context, List<BulkItem> items) {
    final head = _over > 0 ? 1 : 0;
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.6,
      child: ListView.builder(
        itemCount: items.length + head,
        itemBuilder: (context, i) => i < head
            ? UiText('超過 3000 個，後面的 $_over 個沒有檢查',
                style: MFont.inter(12, FontWeight.w600, MColors.againFg))
            : _row(context, i - head, items[i - head]),
      ),
    );
  }

  Widget _row(BuildContext context, int i, BulkItem it) {
    final small = MFont.inter(12, FontWeight.w500, MColors.muted);
    final String label;
    Widget? action;
    switch (it.status) {
      case BulkStatus.existing:
        label = '已在單字本（略過）';
      case BulkStatus.merged:
        label = '併入原形 ${it.word}（一字一張卡，不另加）';
      case BulkStatus.ready:
        label = '可加入';
      case BulkStatus.variant:
        label = it.keepTyped ? '可加入' : '變成原形 ${it.word}';
        action = TextButton(
            key: ValueKey('bulk-keep-$i'),
            onPressed: () => _set(i, it.copyWith(keepTyped: !it.keepTyped)),
            child: UiText(it.keepTyped ? '變成原形 ${it.word}' : '改回原字'));
      case BulkStatus.unknown:
        label = '詞庫沒有，仍可加入';
      case BulkStatus.typo:
        label = '詞庫沒有，是不是：';
        action = Wrap(spacing: 6, children: [
          ActionChip(
              key: ValueKey('bulk-suggest-$i'),
              label: Text(it.suggestion!),
              onPressed: () => _take(i, it.suggestion!)),
          if (!it.include)
            TextButton(
                key: ValueKey('bulk-asis-$i'),
                onPressed: () => _set(i, it.copyWith(include: true)),
                child: const UiText('仍加入原字')),
        ]);
    }
    final detail = [
      if (it.status == BulkStatus.ready || it.status == BulkStatus.variant) ...[
        if (it.isPhrase) ui(context, '片語') else it.pos,
        if (it.level != null) it.level!,
        if (it.meaning.isNotEmpty) it.meaning,
      ],
    ].join(' · ');
    return Padding(
      key: ValueKey('bulk-row-$i'),
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    it.status == BulkStatus.variant && !it.keepTyped
                        ? '${it.typed} → ${it.word}'
                        : it.typed,
                    style: MFont.manrope(15, FontWeight.w700, MColors.ink)),
                UiText(label, style: small),
                if (detail.isNotEmpty) Text(detail, style: small),
                if (action != null) action,
              ],
            ),
          ),
          if (it.status == BulkStatus.unknown ||
              (it.status == BulkStatus.typo && it.include))
            Checkbox(
                key: ValueKey('bulk-include-$i'),
                value: it.include,
                onChanged: (v) => _set(i, it.copyWith(include: v ?? false))),
        ],
      ),
    );
  }
}
