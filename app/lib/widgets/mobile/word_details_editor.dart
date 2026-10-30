import 'dart:convert';

import 'package:flutter/material.dart';

import '../../l10n/ui_text.dart';
import '../../models/word_entry.dart';
import '../../services/learning_content.dart';
import '../../theme/mobile_theme.dart';

/// A dialog draft only. Persistence and update priority use WordEntry.userEdited.
class WordDetailsDraft {
  final WordEntry entry;
  late final String originalMorphology = learningMorphology(entry) ?? '';
  late final String originalEtymology = learningEtymology(entry) ?? '';
  late final morphology = TextEditingController(text: originalMorphology);
  late final etymology = TextEditingController(text: originalEtymology);
  final List<_RelationRow> _related = [];
  final List<_FormRow> _forms = [];
  final List<TextEditingController> _controllers = [];
  bool showErrors = false;

  WordDetailsDraft(this.entry) {
    for (final r in entry.related) {
      addRelation(r);
    }
    for (final f in entry.forms) {
      addForm(f);
    }
  }

  void addRelation([RelatedWord? value]) {
    final row = _RelationRow(value);
    _related.add(row);
    _controllers.addAll([row.word, row.native]);
  }

  void addForm([WordForm? value]) {
    final row = _FormRow(value);
    _forms.add(row);
    _controllers.addAll([row.form, row.label]);
  }

  bool validate() {
    showErrors = true;
    return _related.every((r) => r.word.text.trim().isNotEmpty) &&
        _forms.every((f) => f.form.text.trim().isNotEmpty);
  }

  WordEntry apply(WordEntry updated, Set<String> fields) {
    final relations = [for (final r in _related) r.value];
    final inflections = [for (final f in _forms) f.value];
    if (jsonEncode(relations.map((r) => r.toJson()).toList()) !=
        jsonEncode(entry.related.map((r) => r.toJson()).toList())) {
      fields.add(WordField.related);
    }
    if (jsonEncode(inflections.map((f) => f.toJson()).toList()) !=
        jsonEncode(entry.forms.map((f) => f.toJson()).toList())) {
      fields.add(WordField.forms);
    }
    if (morphology.text.trim() != originalMorphology) {
      fields.add(WordField.morphology);
    }
    if (etymology.text.trim() != originalEtymology) {
      fields.add(WordField.etymology);
    }
    String? nullable(String text) => text.trim().isEmpty ? null : text.trim();
    return updated.copyWith(
      related: relations,
      forms: inflections,
      morphology: fields.contains(WordField.morphology)
          ? () => nullable(morphology.text)
          : null,
      etymology: fields.contains(WordField.etymology)
          ? () => nullable(etymology.text)
          : null,
    );
  }

  void dispose() {
    for (final c in [..._controllers, morphology, etymology]) {
      c.dispose();
    }
  }
}

class _RelationRow {
  final RelatedWord? original;
  final TextEditingController word;
  final TextEditingController native;
  RelationType type;
  _RelationRow(this.original)
      : word = TextEditingController(text: original?.word ?? ''),
        native = TextEditingController(text: original?.native ?? ''),
        type = original?.type ?? RelationType.synonym;

  RelatedWord get value {
    final old = original;
    if (old != null &&
        word.text.trim() == old.word &&
        native.text.trim() == (old.native ?? '') &&
        type == old.type) {
      return old;
    }
    return RelatedWord(word.text.trim(), type,
        native: native.text.trim().isEmpty ? null : native.text.trim());
  }
}

class _FormRow {
  final TextEditingController form;
  final TextEditingController label;
  _FormRow(WordForm? original)
      : form = TextEditingController(text: original?.form ?? ''),
        label = TextEditingController(text: original?.label ?? '');
  WordForm get value => WordForm(form.text.trim(), label.text.trim());
}

class WordDetailsEditor extends StatefulWidget {
  final WordDetailsDraft draft;
  const WordDetailsEditor({super.key, required this.draft});

  @override
  State<WordDetailsEditor> createState() => _WordDetailsEditorState();
}

class _WordDetailsEditorState extends State<WordDetailsEditor> {
  static const labels = {
    RelationType.synonym: '同義字',
    RelationType.antonym: '反義字',
    RelationType.homophone: '同音字',
    RelationType.nearHomophone: '近音字',
    RelationType.similarSpelling: '近形字',
    RelationType.derivation: '衍生字',
    RelationType.associated: '其他相關字',
  };

  Widget heading(String text) => Padding(
        padding: const EdgeInsets.only(top: 12, bottom: 6),
        child: UiText(text,
            style: MFont.manrope(13, FontWeight.w700, MColors.label)),
      );

  Widget field(TextEditingController controller, String label,
          {bool required = false, bool multiline = false}) =>
      TextField(
        controller: controller,
        style: MFont.inter(15, FontWeight.w500, MColors.gray900),
        maxLines: multiline ? null : 1,
        decoration: InputDecoration(
            labelText: label,
            errorText: required &&
                    widget.draft.showErrors &&
                    controller.text.trim().isEmpty
                ? '請填寫或刪除此列'
                : null),
      );

  @override
  Widget build(BuildContext context) {
    final d = widget.draft;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      heading('相關字'),
      for (final r in d._related)
        Padding(
            key: ObjectKey(r),
            padding: const EdgeInsets.only(bottom: 8),
            child: Column(children: [
              Row(children: [
                Expanded(
                    child: DropdownButtonFormField<RelationType>(
                  initialValue: r.type,
                  decoration: const InputDecoration(labelText: '關係類型'),
                  items: [
                    for (final t in RelationType.values)
                      DropdownMenuItem(value: t, child: UiText(labels[t]!))
                  ],
                  onChanged: (value) => setState(() => r.type = value!),
                )),
                IconButton(
                    tooltip: ui(context, '刪除相關字'),
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => setState(() => d._related.remove(r))),
              ]),
              field(r.word, '相關單字', required: true),
              field(r.native, '相關字釋義'),
            ])),
      TextButton.icon(
          onPressed: () => setState(() => d.addRelation()),
          icon: const Icon(Icons.add),
          label: const UiText('新增相關字')),
      heading('詞形變化'),
      for (final f in d._forms)
        Padding(
            key: ObjectKey(f),
            padding: const EdgeInsets.only(bottom: 8),
            child: Column(children: [
              Row(children: [
                Expanded(child: field(f.form, '變化形', required: true)),
                IconButton(
                    tooltip: ui(context, '刪除詞形變化'),
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => setState(() => d._forms.remove(f))),
              ]),
              field(f.label, '變化說明（例如：過去式）'),
            ])),
      TextButton.icon(
          onPressed: () => setState(() => d.addForm()),
          icon: const Icon(Icons.add),
          label: const UiText('新增詞形變化')),
      heading('構詞與詞源'),
      field(d.morphology, '構詞（字根、字首／字尾與解釋）', multiline: true),
      field(d.etymology, '詞源', multiline: true),
      const SizedBox(height: 6),
      const UiText('可直接修改內容；清空構詞或詞源即可刪除。'),
    ]);
  }
}
