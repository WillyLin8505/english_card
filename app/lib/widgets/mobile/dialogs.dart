import 'package:flutter/material.dart';

import '../../models/card_template.dart';
import '../../models/photo.dart';
import '../../models/word_entry.dart';
import '../../services/word_database_repository.dart';
import '../../services/word_selector.dart';
import '../../theme/mobile_theme.dart';

Text _title(String text) =>
    Text(text, style: MFont.manrope(18, FontWeight.w800, MColors.ink));

Text _fieldLabel(String text) =>
    Text(text, style: MFont.manrope(13, FontWeight.w700, MColors.label));

TextStyle get _input => MFont.inter(15, FontWeight.w500, MColors.gray900);

/// 新增單字. Returns the created entry, or null if cancelled. A word + POS
/// pair that already exists is rejected inline (spec: 標準化拼字＋詞性 is
/// the duplicate key).
Future<WordEntry?> showAddWordDialog(
        BuildContext context, WordDatabaseRepository repository) =>
    showDialog<WordEntry>(
        context: context, builder: (_) => _AddWordDialog(repository));

class _AddWordDialog extends StatefulWidget {
  final WordDatabaseRepository repository;

  const _AddWordDialog(this.repository);

  @override
  State<_AddWordDialog> createState() => _AddWordDialogState();
}

class _AddWordDialogState extends State<_AddWordDialog> {
  static const _posOptions = ['noun', 'verb', 'adj.', 'adv.', 'phrase'];

  final _word = TextEditingController();
  final _meaning = TextEditingController();
  String _pos = _posOptions.first;
  String? _level;
  String? _error;

  @override
  void dispose() {
    _word.dispose();
    _meaning.dispose();
    super.dispose();
  }

  void _submit() {
    final word = _word.text.trim();
    final meaning = _meaning.text.trim();
    if (word.isEmpty || meaning.isEmpty) {
      setState(() => _error = '請填寫英文單字與中文釋義');
      return;
    }
    try {
      final entry = widget.repository.addWord(
        word: word,
        pos: _pos,
        meaning: meaning,
        level: _level,
      );
      Navigator.of(context).pop(entry);
    } on DuplicateWordException catch (e) {
      setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: _title('新增單字'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _fieldLabel('英文單字'),
            const SizedBox(height: 6),
            TextField(
              controller: _word,
              autofocus: true,
              style: _input,
              decoration: const InputDecoration(hintText: 'e.g. balcony'),
            ),
            const SizedBox(height: 14),
            _fieldLabel('中文釋義'),
            const SizedBox(height: 6),
            TextField(
              controller: _meaning,
              style: _input,
              decoration: const InputDecoration(hintText: 'e.g. 陽台'),
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 14),
            _fieldLabel('詞性'),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final p in _posOptions)
                  ChoiceChip(
                    label: Text(p),
                    selected: p == _pos,
                    onSelected: (_) => setState(() => _pos = p),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            _fieldLabel('等級（可不選）'),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final l in cefrLevels)
                  ChoiceChip(
                    label: Text(l),
                    selected: l == _level,
                    onSelected: (on) => setState(() => _level = on ? l : null),
                  ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  style: MFont.inter(13, FontWeight.w500, MColors.againFg)),
            ],
            const SizedBox(height: 12),
            Text(
              '音標、例句與翻譯會在背景自動補上。',
              style: MFont.inter(12, FontWeight.w400, MColors.gray500),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(onPressed: _submit, child: const Text('新增')),
      ],
    );
  }
}

/// Add or correct a photo label (spec: AI 英文標籤「可改」).
Future<({String word, String zh})?> showLabelDialog(
  BuildContext context, {
  String title = '新增單字標籤',
  String word = '',
  String zh = '',
}) =>
    showDialog<({String word, String zh})>(
      context: context,
      builder: (_) => _LabelDialog(title: title, word: word, zh: zh),
    );

class _LabelDialog extends StatefulWidget {
  final String title;
  final String word;
  final String zh;

  const _LabelDialog(
      {required this.title, required this.word, required this.zh});

  @override
  State<_LabelDialog> createState() => _LabelDialogState();
}

class _LabelDialogState extends State<_LabelDialog> {
  late final _word = TextEditingController(text: widget.word);
  late final _zh = TextEditingController(text: widget.zh);

  @override
  void dispose() {
    _word.dispose();
    _zh.dispose();
    super.dispose();
  }

  void _submit() {
    if (_word.text.trim().isEmpty) return;
    Navigator.of(context).pop((word: _word.text.trim(), zh: _zh.text.trim()));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: _title(widget.title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _fieldLabel('英文'),
            const SizedBox(height: 6),
            TextField(controller: _word, autofocus: true, style: _input),
            const SizedBox(height: 14),
            _fieldLabel('中文'),
            const SizedBox(height: 6),
            TextField(
                controller: _zh, style: _input, onSubmitted: (_) => _submit()),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('取消')),
          FilledButton(onPressed: _submit, child: const Text('儲存')),
        ],
      );
}

/// After picking a photo: its name and which album it goes in (spec:
/// 存成本機英文相簿). Returns null if cancelled.
Future<({String title, String? albumId})?> showSaveToAlbumDialog(
  BuildContext context, {
  required WordDatabaseRepository repository,
  required String defaultTitle,
  String? albumId,
}) =>
    showDialog<({String title, String? albumId})>(
      context: context,
      builder: (_) => _SaveToAlbumDialog(repository, defaultTitle, albumId),
    );

class _SaveToAlbumDialog extends StatefulWidget {
  final WordDatabaseRepository repository;
  final String defaultTitle;
  final String? albumId;

  const _SaveToAlbumDialog(this.repository, this.defaultTitle, this.albumId);

  @override
  State<_SaveToAlbumDialog> createState() => _SaveToAlbumDialogState();
}

class _SaveToAlbumDialogState extends State<_SaveToAlbumDialog> {
  late final _name = TextEditingController(text: widget.defaultTitle);
  final _newAlbum = TextEditingController();
  late String? _albumId =
      widget.albumId ?? widget.repository.albums.firstOrNull?.id;
  bool _creating = false;

  @override
  void dispose() {
    _name.dispose();
    _newAlbum.dispose();
    super.dispose();
  }

  void _submit() {
    var albumId = _albumId;
    if (_creating && _newAlbum.text.trim().isNotEmpty) {
      albumId = widget.repository.addAlbum(name: _newAlbum.text).id;
    }
    final title =
        _name.text.trim().isEmpty ? widget.defaultTitle : _name.text.trim();
    Navigator.of(context).pop((title: title, albumId: albumId));
  }

  @override
  Widget build(BuildContext context) {
    final albums = widget.repository.albums;
    return AlertDialog(
      title: _title('存到相片冊'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _fieldLabel('照片名稱'),
            const SizedBox(height: 6),
            TextField(controller: _name, style: _input),
            const SizedBox(height: 14),
            _fieldLabel('相片冊'),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final Album a in albums)
                  ChoiceChip(
                    label: Text(a.name),
                    selected: !_creating && a.id == _albumId,
                    onSelected: (_) => setState(() {
                      _creating = false;
                      _albumId = a.id;
                    }),
                  ),
                ChoiceChip(
                  label: const Text('＋ 新相片冊'),
                  selected: _creating,
                  onSelected: (_) => setState(() => _creating = true),
                ),
              ],
            ),
            if (_creating) ...[
              const SizedBox(height: 10),
              TextField(
                controller: _newAlbum,
                autofocus: true,
                style: _input,
                decoration: const InputDecoration(hintText: '相片冊名稱'),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(onPressed: _submit, child: const Text('儲存')),
      ],
    );
  }
}

/// 卡片背面順序: reorder and show/hide the card template's back fields
/// (spec section 4: "使用者可拖曳調整…欄位順序，並選擇顯示、隱藏").
Future<CardTemplate?> showTemplateOrderDialog(
        BuildContext context, CardTemplate template) =>
    showDialog<CardTemplate>(
      context: context,
      builder: (_) => _TemplateOrderDialog(template: template),
    );

class _TemplateOrderDialog extends StatefulWidget {
  final CardTemplate template;

  const _TemplateOrderDialog({required this.template});

  @override
  State<_TemplateOrderDialog> createState() => _TemplateOrderDialogState();
}

class _TemplateOrderDialogState extends State<_TemplateOrderDialog> {
  late final List<TemplateField> _fields = [...widget.template.backFields];

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: _title('卡片背面順序'),
      content: SizedBox(
        width: 340,
        height: 440,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '拖曳調整順序；關閉的欄位不會出現在卡片背面。英文單字固定為標題。',
              style: MFont.inter(13, FontWeight.w400, MColors.gray500),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: ReorderableListView(
                buildDefaultDragHandles: false,
                onReorderItem: (from, to) =>
                    setState(() => _fields.insert(to, _fields.removeAt(from))),
                children: [
                  for (var i = 0; i < _fields.length; i++)
                    ListTile(
                      key: ValueKey(_fields[i].field),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: ReorderableDragStartListener(
                        index: i,
                        child: const Icon(Icons.drag_indicator,
                            color: MColors.label),
                      ),
                      title: Text(
                        _fields[i].field.label,
                        style: MFont.inter(
                          15,
                          FontWeight.w500,
                          _fields[i].visible
                              ? MColors.gray900
                              : MColors.gray500,
                        ),
                      ),
                      trailing: Switch(
                        value: _fields[i].visible,
                        onChanged: (v) => setState(
                            () => _fields[i] = _fields[i].copyWith(visible: v)),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(
          onPressed: () => Navigator.of(context)
              .pop(widget.template.copyWith(backFields: _fields)),
          child: const Text('儲存'),
        ),
      ],
    );
  }
}

/// 「為什麼是這些字？」: every candidate with its recommendation score, or
/// why it wasn't shown (spec section 3: 保存排序依據，方便除錯並解釋為何
/// 出現或未出現).
Future<void> showSelectionReasons(BuildContext context, Selection selection) {
  final shown = {for (final w in selection.words) w.word};
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      builder: (context, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        children: [
          _title('為什麼是這些字？'),
          const SizedBox(height: 6),
          Text(
            'AI 先從照片找出候選詞，再由這台裝置依程度、未知機率、圖片關聯、實用性與詞性多樣性打分，'
            '最多選 5 個；名詞最多 3 個，同義詞只留一個。',
            style: MFont.inter(13, FontWeight.w400, MColors.gray500),
          ),
          const SizedBox(height: 12),
          for (final s in selection.scored)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 22,
                    child: Icon(
                      shown.contains(s.word)
                          ? Icons.check_circle
                          : Icons.circle_outlined,
                      size: 16,
                      color: shown.contains(s.word)
                          ? MColors.success
                          : MColors.label,
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                            '${s.word}  ${s.candidate.meaning}  (${s.candidate.pos})',
                            style: MFont.manrope(
                                14, FontWeight.w800, MColors.ink)),
                        Text(
                          s.rejected ?? s.explain(),
                          style: MFont.manrope(
                              12,
                              FontWeight.w600,
                              s.rejected == null
                                  ? MColors.muted
                                  : MColors.againFg),
                        ),
                        if (s.candidate.evidence.isNotEmpty)
                          Text('照片中：${s.candidate.evidence}',
                              style: MFont.manrope(
                                  12, FontWeight.w500, MColors.label)),
                      ],
                    ),
                  ),
                  Text(s.base.toStringAsFixed(2),
                      style: MFont.inter(12, FontWeight.w600, MColors.gray500)),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

/// Edits a word's shared data (spec section 7: 使用者可編輯所有 AI 與字典
/// 資料。使用者修改值優先於後續自動更新). Returns the edited entry and the
/// fields changed, or null.
Future<(WordEntry, Set<String>)?> showEditWordDialog(
        BuildContext context, WordEntry entry) =>
    showDialog<(WordEntry, Set<String>)>(
      context: context,
      builder: (_) => _EditWordDialog(entry),
    );

class _EditWordDialog extends StatefulWidget {
  final WordEntry entry;

  const _EditWordDialog(this.entry);

  @override
  State<_EditWordDialog> createState() => _EditWordDialogState();
}

class _EditWordDialogState extends State<_EditWordDialog> {
  static const _posOptions = ['noun', 'verb', 'adj.', 'adv.', 'phrase'];

  late final _meaning = TextEditingController(text: widget.entry.meaning);
  late final _definition =
      TextEditingController(text: widget.entry.definition ?? '');
  late final _ipa = TextEditingController(text: widget.entry.ipa ?? '');
  late String _pos = widget.entry.pos;
  late String? _level = widget.entry.level;
  late final List<TextEditingController> _translations = [
    for (final x in widget.entry.examples)
      TextEditingController(text: x.translation ?? ''),
  ];

  @override
  void dispose() {
    for (final c in [_meaning, _definition, _ipa, ..._translations]) {
      c.dispose();
    }
    super.dispose();
  }

  void _submit() {
    final e = widget.entry;
    final fields = <String>{};
    String? blankToNull(String s) => s.trim().isEmpty ? null : s.trim();
    if (_meaning.text.trim() != e.meaning) fields.add(WordField.meaning);
    if (blankToNull(_definition.text) != e.definition) {
      fields.add(WordField.definition);
    }
    if (blankToNull(_ipa.text) != e.ipa) fields.add(WordField.ipa);
    if (_pos != e.pos) fields.add(WordField.pos);
    if (_level != e.level) fields.add(WordField.level);
    var examplesChanged = false;
    final examples = [
      for (final (i, x) in e.examples.indexed)
        if (_translations[i].text.trim() == (x.translation ?? ''))
          x
        else
          WordExample(
            text: x.text,
            translation: blankToNull(_translations[i].text),
            source: x.source,
            aiGenerated: x.aiGenerated,
          ),
    ];
    for (final (i, x) in examples.indexed) {
      if (!identical(x, e.examples[i])) examplesChanged = true;
    }
    if (examplesChanged) fields.add(WordField.examples);
    if (fields.isEmpty) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pop((
      e.copyWith(
        meaning: _meaning.text.trim(),
        definition: () => blankToNull(_definition.text),
        ipa: () => blankToNull(_ipa.text),
        ipaSource: fields.contains(WordField.ipa) ? () => 'user' : null,
        pos: _pos,
        level: () => _level,
        levelSource: fields.contains(WordField.level) ? () => 'user' : null,
        examples: examples,
      ),
      fields,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: _title('編輯「${widget.entry.word}」'),
      content: SizedBox(
        width: 360,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _fieldLabel('釋義'),
              const SizedBox(height: 6),
              TextField(controller: _meaning, style: _input),
              const SizedBox(height: 12),
              _fieldLabel('解釋'),
              const SizedBox(height: 6),
              TextField(controller: _definition, style: _input, maxLines: null),
              const SizedBox(height: 12),
              _fieldLabel('音標'),
              const SizedBox(height: 6),
              TextField(controller: _ipa, style: _input),
              const SizedBox(height: 12),
              _fieldLabel('詞性'),
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final p in {..._posOptions, widget.entry.pos})
                    if (p.isNotEmpty)
                      ChoiceChip(
                        label: Text(p),
                        selected: p == _pos,
                        onSelected: (_) => setState(() => _pos = p),
                      ),
                ],
              ),
              const SizedBox(height: 12),
              _fieldLabel('等級'),
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final l in cefrLevels)
                    ChoiceChip(
                      label: Text(l),
                      selected: l == _level,
                      onSelected: (on) =>
                          setState(() => _level = on ? l : null),
                    ),
                ],
              ),
              if (widget.entry.examples.isNotEmpty) ...[
                const SizedBox(height: 12),
                _fieldLabel('例句翻譯'),
                for (final (i, x) in widget.entry.examples.indexed) ...[
                  const SizedBox(height: 8),
                  Text(x.text,
                      style: MFont.inter(13, FontWeight.w600, MColors.gray900)),
                  TextField(controller: _translations[i], style: _input),
                ],
              ],
              const SizedBox(height: 12),
              Text('你改過的欄位之後不會被自動更新覆蓋。',
                  style: MFont.inter(12, FontWeight.w400, MColors.gray500)),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消')),
        FilledButton(onPressed: _submit, child: const Text('儲存')),
      ],
    );
  }
}
