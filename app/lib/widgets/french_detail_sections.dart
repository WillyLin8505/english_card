// Card #1220 / 問題回報 #1672: the French blocks of the pack word page —
// title with article and gender, conjugation tables, adjective grid.
// Labels are zh UI keys (ui_catalog), so they follow the native language.
import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../services/french_detail.dart';
import '../theme/mobile_theme.dart';

const _irregularColor = Color(0xFFD9480F);

/// 「le chat」/「l'arbre」 with m./f. beside it and the plural; null parts
/// are left out. [gender] is the pack's fr_gender.
class FrenchTitle extends StatelessWidget {
  final String lemma;
  final String? gender;
  final String? plural;
  final bool? hAspire;
  const FrenchTitle(this.lemma,
      {super.key, this.gender, this.plural, this.hAspire});

  @override
  Widget build(BuildContext context) {
    final g = gender;
    final shown = g == null
        ? lemma
        : frenchDefiniteArticle(lemma, g, hAspire: hAspire) ?? lemma;
    final tag = switch (g) {
      'm' => 'm.',
      'f' => 'f.',
      'm/f' => 'm./f.',
      'pl' => 'pl.',
      _ => null,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Flexible(
              child: Text(shown,
                  key: const ValueKey('fr-title'),
                  style: MFont.manrope(28, FontWeight.w800, MColors.ink)),
            ),
            if (tag != null) ...[
              const SizedBox(width: 8),
              Text(tag,
                  key: const ValueKey('fr-gender-tag'),
                  style: MFont.manrope(16, FontWeight.w700, MColors.primary)),
            ],
          ],
        ),
        if (plural != null && plural!.isNotEmpty) ...[
          const SizedBox(height: 2),
          Row(children: [
            UiText('複數', style: MFont.caption),
            Text(' · ', style: MFont.caption),
            Text(plural!, key: const ValueKey('fr-plural'), style: MFont.body),
          ]),
        ],
        if (hAspire == true) ...[
          const SizedBox(height: 2),
          UiText('h aspiré：不連音、不省略（le héros，不是 l\'héros）',
              key: const ValueKey('fr-h-aspire'), style: MFont.caption),
        ],
      ],
    );
  }
}

class FrenchVerbSection extends StatefulWidget {
  final FrenchVerb verb;
  const FrenchVerbSection(this.verb, {super.key});
  @override
  State<FrenchVerbSection> createState() => _FrenchVerbSectionState();
}

class _FrenchVerbSectionState extends State<FrenchVerbSection> {
  bool _more = false;

  Widget _table(FrenchTenseTable t) => Container(
        key: ValueKey('fr-tense-${t.tense.code}'),
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: MSpace.xs),
        padding: const EdgeInsets.all(MSpace.sm),
        decoration: MDecor.softCard(color: MColors.surfaceSoft),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            UiText(t.tense.label,
                style: MFont.manrope(13, FontWeight.w800, MColors.primaryDeep)),
            const SizedBox(height: 4),
            for (final c in t.cells)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 1),
                child: Text(c.text,
                    style: MFont.manrope(
                        15,
                        c.irregular ? FontWeight.w800 : FontWeight.w600,
                        c.irregular ? _irregularColor : MColors.ink)),
              ),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final v = widget.verb;
    final facts = <String>[
      if (v.group != null) '${v.group} ${ui(context, '動詞')}',
      if (v.irregular) ui(context, '不規則動詞'),
      if (v.pronominal) ui(context, '代動詞'),
      if (v.auxiliaries.isNotEmpty)
        '${ui(context, '助動詞')} ${v.auxiliaries.join('／')}',
    ];
    return Column(
      key: const ValueKey('fr-verb'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        UiText('動詞變位', style: MFont.titleSm),
        const SizedBox(height: MSpace.xs),
        if (facts.isNotEmpty)
          Wrap(spacing: MSpace.xs, runSpacing: 4, children: [
            for (final f in facts)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: MDecor.chipSurface(active: false),
                child: Text(f, style: MFont.caption),
              ),
          ]),
        const SizedBox(height: MSpace.xs),
        if (v.pastParticiple != null || v.presentParticiple != null)
          Padding(
            padding: const EdgeInsets.only(bottom: MSpace.xs),
            child: Wrap(spacing: MSpace.md, children: [
              if (v.presentParticiple != null)
                Row(mainAxisSize: MainAxisSize.min, children: [
                  UiText('現在分詞', style: MFont.caption),
                  Text('  ${v.presentParticiple}', style: MFont.body),
                ]),
              if (v.pastParticiple != null)
                Row(mainAxisSize: MainAxisSize.min, children: [
                  UiText('過去分詞', style: MFont.caption),
                  Text('  ${v.pastParticiple}', style: MFont.body),
                ]),
            ]),
          ),
        for (final t in v.common) _table(t),
        if (v.more.isNotEmpty) ...[
          if (_more)
            for (final t in v.more) _table(t),
          TextButton(
            key: const ValueKey('fr-more-tenses'),
            onPressed: () => setState(() => _more = !_more),
            child: UiText(_more ? '收起時態' : '顯示更多時態'),
          ),
        ],
      ],
    );
  }
}

class FrenchAdjectiveSection extends StatelessWidget {
  final FrenchAdjective adjective;
  const FrenchAdjectiveSection(this.adjective, {super.key});

  Widget _cell(BuildContext context, String label, String? value) => Expanded(
        child: Container(
          margin: const EdgeInsets.all(2),
          padding: const EdgeInsets.all(MSpace.sm),
          decoration: MDecor.softCard(color: MColors.surfaceSoft),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              UiText(label, style: MFont.caption),
              Text(value ?? '—',
                  style: MFont.manrope(16, FontWeight.w700, MColors.ink)),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final a = adjective;
    return Column(
      key: const ValueKey('fr-adjective'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        UiText('形容詞變化', style: MFont.titleSm),
        const SizedBox(height: MSpace.xs),
        Row(children: [
          _cell(context, '陽性單數', a.masculine),
          _cell(context, '陰性單數', a.feminine),
        ]),
        Row(children: [
          _cell(context, '陽性複數', a.masculinePlural),
          _cell(context, '陰性複數', a.femininePlural),
        ]),
        if (a.beforeVowel != null)
          Row(children: [
            _cell(context, '陽性單數（母音前）', a.beforeVowel),
            const Expanded(child: SizedBox()),
          ]),
      ],
    );
  }
}
