import '../../l10n/ui_text.dart';
import 'package:flutter/material.dart';

import '../../models/card_template.dart';
import '../../models/photo.dart';
import '../../models/word_entry.dart';
import '../../services/card_report.dart';
import '../../services/word_database_repository.dart';
import '../../services/word_selector.dart';
import '../../theme/mobile_theme.dart';
import 'word_details_editor.dart';

Widget _title(String text) =>
    UiText(text, style: MFont.manrope(18, FontWeight.w800, MColors.ink));

Widget _fieldLabel(String text) =>
    UiText(text, style: MFont.manrope(13, FontWeight.w700, MColors.label));

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
      setState(() => _error = '請填寫{L}單字與{N}釋義');
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
            _fieldLabel('{L}單字'),
            const SizedBox(height: 6),
            TextField(
              controller: _word,
              autofocus: true,
              style: _input,
              decoration: const InputDecoration(hintText: 'e.g. balcony'),
            ),
            const SizedBox(height: 14),
            _fieldLabel('{N}釋義'),
            const SizedBox(height: 6),
            TextField(
              controller: _meaning,
              style: _input,
              decoration: InputDecoration(hintText: ui(context, 'e.g. 陽台')),
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
              UiText(_error!,
                  style: MFont.inter(13, FontWeight.w500, MColors.againFg)),
            ],
            const SizedBox(height: 12),
            UiText(
              '音標、例句與翻譯會在背景自動補上。',
              style: MFont.inter(12, FontWeight.w400, MColors.gray500),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const UiText('取消')),
        FilledButton(onPressed: _submit, child: const UiText('新增')),
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
  String? hint,
}) =>
    showDialog<({String word, String zh})>(
      context: context,
      builder: (_) =>
          _LabelDialog(title: title, word: word, zh: zh, hint: hint),
    );

class _LabelDialog extends StatefulWidget {
  final String title;
  final String word;
  final String zh;
  final String? hint;

  const _LabelDialog(
      {required this.title, required this.word, required this.zh, this.hint});

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
            _fieldLabel('{L}'),
            const SizedBox(height: 6),
            TextField(controller: _word, autofocus: true, style: _input),
            const SizedBox(height: 14),
            _fieldLabel('{N}'),
            const SizedBox(height: 6),
            TextField(
                controller: _zh, style: _input, onSubmitted: (_) => _submit()),
            if (widget.hint != null) ...[
              const SizedBox(height: 10),
              UiText(widget.hint!,
                  style: MFont.manrope(12, FontWeight.w600, MColors.label)),
            ],
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const UiText('取消')),
          FilledButton(onPressed: _submit, child: const UiText('儲存')),
        ],
      );
}

/// Default name for a new photo, the same for the camera and the picker
/// (問題回報 #313): month/day plus time, e.g. 「10/19 14:32」.
String defaultPhotoTitle(DateTime now) =>
    '${now.month}/${now.day} ${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';

typedef SavePhotoChoice = ({
  String title,
  String? albumId,
  PhotoScanMode scanMode,
});

/// After picking a photo: which album it goes in (spec: 存成本機英文相簿).
/// The name is automatic (the default title; rename it in 照片詳情), and it
/// always looks for both things and printed text (問題回報 #409: no name
/// or 找什麼 questions). Returns null if cancelled.
Future<SavePhotoChoice?> showSaveToAlbumDialog(
  BuildContext context, {
  required WordDatabaseRepository repository,
  required String defaultTitle,
  String? albumId,
}) =>
    showDialog<SavePhotoChoice>(
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
  final _newAlbum = TextEditingController();
  late String? _albumId =
      widget.albumId ?? widget.repository.albums.firstOrNull?.id;
  bool _creating = false;

  @override
  void dispose() {
    _newAlbum.dispose();
    super.dispose();
  }

  void _submit() {
    if (_creating && _newAlbum.text.trim().isEmpty) return;
    if (!_creating && _albumId == null) return;
    var albumId = _albumId;
    if (_creating && _newAlbum.text.trim().isNotEmpty) {
      albumId = widget.repository.addAlbum(name: _newAlbum.text).id;
    }
    Navigator.of(context).pop((
      title: widget.defaultTitle,
      albumId: albumId,
      scanMode: PhotoScanMode.both,
    ));
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
                  label: const UiText('＋ 新相片冊'),
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
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(hintText: ui(context, '相片冊名稱')),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const UiText('取消')),
        FilledButton(
          onPressed:
              (_creating ? _newAlbum.text.trim().isNotEmpty : _albumId != null)
                  ? _submit
                  : null,
          child: const UiText('儲存'),
        ),
      ],
    );
  }
}

/// The picked picture is already in the 相片冊 (card #217, spec §7's
/// deferred 重複加入同一照片). Returns false to open [existing] instead,
/// true to add a second copy anyway, null if dismissed.
Future<bool?> showDuplicatePhotoDialog(
  BuildContext context, {
  required Photo existing,
  required WordDatabaseRepository repository,
}) {
  final album =
      existing.albumId == null ? null : repository.album(existing.albumId!);
  final where = album == null ? '' : '相片冊「${album.name}」的';
  return showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: _title('這張照片已經加入過'),
      content: UiText(
        '它就是$where「${existing.title}」。要打開原本的照片，還是再加入一張？',
        style: MFont.inter(14, FontWeight.w500, MColors.gray900),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const UiText('仍要再加入')),
        FilledButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const UiText('打開原本的照片')),
      ],
    ),
  );
}

/// 複習畫面「刪除此卡片」誤觸就直接封存、沒有任何回饋（問題回報 #262）：
/// 先二次確認，封存後才由呼叫端用 SnackBar + 復原 action 給回饋。
Future<bool> showDeleteCardDialog(BuildContext context, String word) =>
    showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: _title('移除「$word」？'),
        content: UiText(
          '這張卡片會從複習移除，並加入「已學會」。之後可以在單字本裡復原。',
          style: MFont.inter(14, FontWeight.w500, MColors.gray900),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('移除')),
        ],
      ),
    ).then((v) => v ?? false);

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
            UiText(
              '拖曳調整順序；關閉的欄位不會出現在卡片背面。{L}單字固定為標題。',
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
            child: const UiText('取消')),
        FilledButton(
          onPressed: () => Navigator.of(context)
              .pop(widget.template.copyWith(backFields: _fields)),
          child: const UiText('儲存'),
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
          UiText(
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
                          UiText('照片中：${s.candidate.evidence}',
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
  late final _details = WordDetailsDraft(widget.entry);
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
    _details.dispose();
    for (final c in [_meaning, _definition, _ipa, ..._translations]) {
      c.dispose();
    }
    super.dispose();
  }

  void _submit() {
    if (!_details.validate()) {
      setState(() {});
      return;
    }
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
    final withDetails = _details.apply(e, fields);
    if (fields.isEmpty) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pop((
      withDetails.copyWith(
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
              WordDetailsEditor(draft: _details),
              const SizedBox(height: 12),
              UiText('你改過的欄位之後不會被自動更新覆蓋。',
                  style: MFont.inter(12, FontWeight.w400, MColors.gray500)),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const UiText('取消')),
        FilledButton(onPressed: _submit, child: const UiText('儲存')),
      ],
    );
  }
}

/// 回報此卡片 (問題回報 #316): pick what is wrong and add a line; the word,
/// sense, photo, card type and app version are attached for the learner.
/// Returns true when the report was sent, false when it was kept on the
/// device to send later, null when cancelled.
Future<bool?> showCardReportDialog(
  BuildContext context, {
  required String word,
  required String pos,
  String? meaning,
  String? photoId,
  String cardType = '',
  String apiKey = '',
  CardReportService? service,
}) =>
    showDialog<bool>(
      context: context,
      builder: (_) => _CardReportDialog(
        word: word,
        pos: pos,
        meaning: meaning,
        photoId: photoId,
        cardType: cardType,
        apiKey: apiKey,
        service: service ?? CardReportService.instance,
      ),
    );

class _CardReportDialog extends StatefulWidget {
  final String word, pos, cardType, apiKey;
  final String? meaning, photoId;
  final CardReportService service;

  const _CardReportDialog({
    required this.word,
    required this.pos,
    required this.cardType,
    required this.apiKey,
    required this.service,
    this.meaning,
    this.photoId,
  });

  @override
  State<_CardReportDialog> createState() => _CardReportDialogState();
}

class _CardReportDialogState extends State<_CardReportDialog> {
  String _kind = CardReport.kinds.first.$1;
  final _note = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() => _sending = true);
    final sent = await widget.service.submit(
      CardReport(
        kind: _kind,
        note: _note.text,
        word: widget.word,
        pos: widget.pos,
        meaning: widget.meaning,
        photoId: widget.photoId,
        cardType: widget.cardType,
      ),
      apiKey: widget.apiKey,
    );
    if (mounted) Navigator.of(context).pop(sent);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: _title('回報「${widget.word}」這張卡'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _fieldLabel('哪裡有問題？'),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final k in CardReport.kinds)
                  ChoiceChip(
                    label: UiText(k.$2),
                    selected: _kind == k.$1,
                    onSelected: (_) => setState(() => _kind = k.$1),
                  ),
              ]),
              const SizedBox(height: 16),
              _fieldLabel('說明（一句話就好）'),
              const SizedBox(height: 8),
              TextField(
                controller: _note,
                style: _input,
                minLines: 2,
                maxLines: 4,
                maxLength: 300,
                decoration: const InputDecoration(border: OutlineInputBorder()),
              ),
              UiText('會一併附上這張卡的單字、詞性、義項、照片與 App 版本。',
                  style: MFont.inter(12, FontWeight.w500, MColors.label)),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: _sending ? null : () => Navigator.of(context).pop(),
              child: const UiText('取消')),
          FilledButton(
              onPressed: _sending ? null : _send, child: const UiText('送出')),
        ],
      );
}
