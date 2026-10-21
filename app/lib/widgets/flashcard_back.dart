part of '../screens/flashcard_screen.dart';

/// The language pack's recording of [entry] in [accent] ("en-GB" /
/// "en-US"), or the entry's own audio when it is in that accent; null
/// means the speaker falls back to TTS in that accent.
String? accentAudioUrl(WordEntry entry, String accent) {
  final pack = LexiconPack.instance;
  final source = (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
  final aliases = accent == 'en-GB' ? {'uk', 'gb', 'en-gb'} : {'us', 'en-us'};
  final recording = source?.recordings
      .where((r) => aliases.contains(r.accent?.toLowerCase()))
      .firstOrNull;
  if (recording != null) {
    return packRecordingUrl(pack.mediaBase, recording.path);
  }
  if (aliases.contains(entry.accent?.toLowerCase())) return entry.audioUrl;
  return null;
}

/// Plays [entry] in one accent; tells the learner when nothing was heard.
Future<bool> playAccent(
    BuildContext context, WordEntry entry, String accent) async {
  final speaker = AppScope.of(context).speaker;
  final ok = await speaker.say(entry.word,
      language: entry.language,
      accent: accent,
      audioUrl: accentAudioUrl(entry, accent));
  if (!ok && context.mounted) {
    showToast(context, '播放發音失敗，請檢查音量或稍後再試');
  }
  return ok;
}

/// Card #251: when the card turns, the word is heard in both accents,
/// British first and then American, one after the other.
Future<void> playBothAccents(BuildContext context, WordEntry entry) async {
  for (final accent in const ['en-GB', 'en-US']) {
    if (!context.mounted) return;
    if (!await playAccent(context, entry, accent)) return;
  }
}

/// Which English words on the card back are in the learner's own word
/// database (card #251 item 9): tapping one opens that word's details; a
/// word that is not there is plain text. Headwords and their forms, with
/// the pack's forms for linked entries (went → go), phrases included.
class WordLinks {
  final Map<String, String> _idByText;
  final int _maxWords;

  WordLinks._(this._idByText, this._maxWords);

  factory WordLinks.of(WordDatabaseRepository repo) {
    final pack = LexiconPack.instance;
    final byText = <String, String>{};
    var maxWords = 1;
    void add(String text, String id) {
      final key = text.trim().toLowerCase();
      if (key.isEmpty) return;
      byText.putIfAbsent(key, () => id);
      final n = key.split(' ').length;
      if (n > maxWords) maxWords = n;
    }

    for (final e in repo.entries) {
      if (repo.isArchived(e.id)) continue;
      add(e.word, e.id);
      for (final f in e.forms) {
        add(f.form, e.id);
      }
      final source = e.lexemeId == null ? null : pack.byId(e.lexemeId!);
      for (final f in source?.forms ?? const <LexForm>[]) {
        add(f.form, e.id);
      }
    }
    return WordLinks._(byText, maxWords.clamp(1, 5));
  }

  static final _token = RegExp(r"[A-Za-z]+(?:['’-][A-Za-z]+)*");

  /// The target spelled [text] (a word or phrase): the learner's entry id,
  /// else `pack:<id>` for a word only the dictionary has (問題回報 #406: every
  /// word on the card opens, in the learner's words or not), else null.
  String? idFor(String text) {
    final key = text.trim().toLowerCase();
    final own = _idByText[key] ??
        (key.endsWith("'s") || key.endsWith('’s')
            ? _idByText[key.substring(0, key.length - 2)]
            : null);
    if (own != null) return own;
    final lemma = key.endsWith("'s") || key.endsWith('’s')
        ? key.substring(0, key.length - 2)
        : key;
    final hit = LexiconPack.instance.isEmpty
        ? null
        : LexiconPack.instance.lookup(lemma);
    return hit == null ? null : '$packPrefix${hit.entry.id}';
  }

  static const packPrefix = 'pack:';

  /// [text] cut into runs: plain text, and linked words with the entry
  /// each one opens. The longest phrase in the database wins at each spot.
  List<({String text, String? id})> segments(String text) {
    final tokens = _token.allMatches(text).toList();
    final out = <({String text, String? id})>[];
    var cursor = 0;
    void plain(int end) {
      if (end > cursor) out.add((text: text.substring(cursor, end), id: null));
      cursor = end;
    }

    var i = 0;
    while (i < tokens.length) {
      String? id;
      var n = 0;
      for (var len = math.min(_maxWords, tokens.length - i); len >= 1; len--) {
        final span = text.substring(tokens[i].start, tokens[i + len - 1].end);
        // A phrase is its words joined by single spaces only.
        if (len > 1 && span.contains(RegExp(r'[^A-Za-z\x27’\- ]'))) continue;
        final hit = idFor(span.replaceAll(RegExp(r'\s+'), ' '));
        if (hit != null) {
          id = hit;
          n = len;
          break;
        }
      }
      if (id == null) {
        i++;
        continue;
      }
      plain(tokens[i].start);
      final end = tokens[i + n - 1].end;
      out.add((text: text.substring(cursor, end), id: id));
      cursor = end;
      i += n;
    }
    plain(text.length);
    return out;
  }
}

/// Opens what [id] (from [WordLinks.idFor]) names: the learner's word, or
/// the dictionary's page for a word that is not in their database yet.
void openWordLink(BuildContext context, String id,
    [ValueChanged<String>? custom]) {
  if (custom != null) return custom(id);
  if (id.startsWith(WordLinks.packPrefix)) {
    final wordId = int.tryParse(id.substring(WordLinks.packPrefix.length));
    if (wordId == null) return;
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => DatabaseWordScreen(wordId: wordId)));
    return;
  }
  AppScope.of(context).navigator.openWord(id);
}

/// Text in which every English word that is in the learner's database is a
/// link to its details (card #251 item 9).
class LinkedText extends StatefulWidget {
  final String text;
  final TextStyle style;
  final WordLinks? links;
  final ValueChanged<String>? onOpenWord;

  const LinkedText(this.text,
      {super.key, required this.style, this.links, this.onOpenWord});

  @override
  State<LinkedText> createState() => _LinkedTextState();
}

class _LinkedTextState extends State<LinkedText> {
  final _recognizers = <TapGestureRecognizer>[];

  void _clear() {
    for (final r in _recognizers) {
      r.dispose();
    }
    _recognizers.clear();
  }

  @override
  void dispose() {
    _clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _clear();
    final links = widget.links;
    if (links == null) return Text(widget.text, style: widget.style);
    final linkStyle = widget.style.copyWith(
      color: MColors.primaryDeep,
      decoration: TextDecoration.underline,
      decorationColor: MColors.primary.withValues(alpha: 0.45),
      decorationThickness: 1.5,
    );
    final spans = <InlineSpan>[];
    for (final s in links.segments(widget.text)) {
      final id = s.id;
      if (id == null) {
        spans.add(TextSpan(text: s.text));
        continue;
      }
      final recognizer = TapGestureRecognizer()
        ..onTap = () => openWordLink(context, id, widget.onOpenWord);
      _recognizers.add(recognizer);
      spans.add(
          TextSpan(text: s.text, style: linkStyle, recognizer: recognizer));
    }
    return Text.rich(TextSpan(style: widget.style, children: spans));
  }
}

class FlashcardBack extends StatelessWidget {
  final WordEntry entry;
  // The usage/sense this exercise actually tested; overrides entry.pos and
  // entry.meaning on the back so they match the front's question rather
  // than the entry's default usage (問題回報 #4).
  final String? activePos;
  final String? activeMeaning;
  final String? activeDefinition;
  final LearningCard card;
  final Photo? photo;
  final LabelPoint? anchor;
  final String? photoCredit;

  /// Every photo of the word, for swiping between them (card #251 item 8).
  /// Empty: only [photo] is shown.
  final List<CardPhoto> photos;
  final ValueChanged<int>? onPhotoSelected;
  final bool? answerCorrect;
  final String? submittedAnswer;
  final String? correctAnswer;
  final CardTemplate template;
  final String learnerLevel;
  final VoidCallback onPlay;
  final VoidCallback onOpen;

  /// Opens another word's details from a tapped word (item 9); the app
  /// navigator when null.
  final ValueChanged<String>? onOpenWord;

  const FlashcardBack({
    super.key,
    required this.entry,
    this.activePos,
    this.activeMeaning,
    this.activeDefinition,
    required this.card,
    required this.photo,
    required this.anchor,
    this.photoCredit,
    this.photos = const [],
    this.onPhotoSelected,
    this.answerCorrect,
    this.submittedAnswer,
    this.correctAnswer,
    required this.template,
    required this.learnerLevel,
    required this.onPlay,
    required this.onOpen,
    this.onOpenWord,
  });

  LexEntry? get _source {
    final pack = LexiconPack.instance;
    final byId = entry.lexemeId == null ? null : pack.byId(entry.lexemeId!);
    // A saved lexeme id can name another part of speech of the same spelling
    // (out 「出」 the adverb, id of out the adjective): its synonyms (knocked
    // out, forbidden…) belong to a different meaning. Follow the card's own
    // part of speech then (問題回報 #384). The usage tested this round wins:
    // sweep saved as a noun but reviewed as the verb lists swept/sweeping,
    // not 複數 sweeps (卡 #227 第 109 輪).
    final pos = (activePos ?? entry.pos).trim();
    if (byId != null &&
        pos.isNotEmpty &&
        byId.pos != LexiconPack.packPos(pos)) {
      final same = pack.lookup(entry.word, pos: pos)?.entry;
      if (same != null && same.pos == LexiconPack.packPos(pos)) return same;
    }
    return byId ?? pack.lookup(entry.word, pos: entry.pos)?.entry;
  }

  /// Card #416: the first [initial] items, the rest behind 顯示更多.
  Widget _items(CardBackField field, List<Widget> items, {int initial = 10000}) =>
      ShowMoreItems(initial: initial, children: items);

  Widget? _configuredField(BuildContext context, TemplateField setting,
      WordLinks links, CardLook look) {
    final block = _field(context, setting.field, links, look);
    if (block is _Block) return _Block(block.label, block.child);
    return block;
  }

  /// Related words of [kinds] with their native meaning: the learner's own
  /// edits when there are any, else the pack's (very rare ones stay hidden).
  /// Words without a native meaning are left off the back (#437; they stay
  /// on the word detail page). Words already in [shown] (an earlier block)
  /// are skipped, and the returned ones are added to it, so one word is
  /// never on the back twice.
  List<({String word, String meaning})> _relations(List<String> kinds,
      {required int maxItems, Set<String>? shown}) {
    final seen = <String>{entry.word.toLowerCase(), ...?shown};
    final out = <({String word, String meaning, int level})>[];
    if (entry.userEdited.contains(WordField.related)) {
      final types = {for (final k in kinds) relationTypeFromKey(k)};
      for (final r in entry.related) {
        if (types.contains(r.type) &&
            !r.hideByDefault &&
            (r.native ?? '').trim().isNotEmpty &&
            seen.add(r.word.toLowerCase())) {
          out.add((word: r.word, meaning: r.native!.trim(), level: 0));
        }
      }
    } else {
      final source = _source;
      if (source != null) {
        for (final r in source.relations) {
          if (kinds.contains(r.relation) &&
              !r.hideByDefault &&
              r.word.trim().isNotEmpty &&
              (r.native ?? '').trim().isNotEmpty &&
              seen.add(r.word.toLowerCase())) {
            out.add((
              word: r.word,
              meaning: r.native!.trim(),
              // Easier words first.
              level: r.cefr == null ? 50 : levelIndex(r.cefr),
            ));
          }
        }
      }
    }
    final order = out.indexed.toList()
      ..sort((a, b) {
        final c = a.$2.level.compareTo(b.$2.level);
        return c != 0 ? c : a.$1.compareTo(b.$1);
      });
    final picked = [
      for (final (_, r) in order.take(maxItems))
        (word: r.word, meaning: r.meaning)
    ];
    shown?.addAll(picked.map((r) => r.word.toLowerCase()));
    return picked;
  }

  static const _formOrder = [
    '第三人稱單數',
    '過去式',
    '過去分詞',
    '現在分詞',
    '複數',
    '比較級',
    '最高級',
    '名詞',
    '形容詞',
    '副詞',
    '動詞',
  ];

  static String? _formKind(String field, String? label) {
    switch (field) {
      case 'verb_base':
        return null; // the headword itself
      case 'noun_plural':
        return '複數';
      case 'verb_past':
        return '過去式';
      case 'verb_past_participle':
        return '過去分詞';
      case 'verb_present_participle':
        return '現在分詞';
      case 'verb_third_person':
        return '第三人稱單數';
      case 'adj_comparative':
        return '比較級';
      case 'adj_superlative':
        return '最高級';
    }
    final l = formLabel(label ?? field);
    return l == '變化形' ? null : l;
  }

  /// The kinds of form this word has, each with one word, in the fixed
  /// order of [_formOrder]: the pack's inflections, the learner's own
  /// forms for kinds the pack lacks, then the word family (decide →
  /// decision, decisive, decisively) by part of speech.
  List<({String kind, String word})> _formCells() {
    final pack = LexiconPack.instance;
    final source = _source;
    // Only the lemma itself is left out: a card saved as 「went」 still lists
    // went as go's 過去式, so the lemma's forms stay complete (card #251).
    final head = (source?.lemma ?? entry.word).trim().toLowerCase();
    final byKind = <String, String>{};
    void add(String? kind, String form) {
      final f = form.trim();
      if (kind == null || f.isEmpty || f.toLowerCase() == head) return;
      byKind.putIfAbsent(kind, () => f);
    }

    for (final f in source?.forms ?? const <LexForm>[]) {
      add(_formKind(f.field, f.label), f.form);
    }
    // The entry's own forms belong to its saved part of speech; reviewed as
    // another one they would mix 複數 sweeps into the verb's forms.
    final otherPos = activePos != null &&
        LexiconPack.packPos(activePos!) != LexiconPack.packPos(entry.pos);
    for (final f in otherPos ? const <WordForm>[] : entry.forms) {
      add(_formKind('', f.label), f.form);
    }
    if (source != null) {
      const posKind = {
        'noun': '名詞',
        'adj': '形容詞',
        'adv': '副詞',
        'verb': '動詞',
      };
      final best = <String, ({String word, double zipf})>{};
      for (final r in source.relations) {
        if (r.relation != 'derived_terms' || r.hideByDefault) continue;
        final w = r.word.trim();
        final hit = pack.lookup(w)?.entry;
        if (w.isEmpty ||
            hit == null ||
            hit.normalized != LexiconPack.normalize(w)) {
          continue;
        }
        final kind = posKind[hit.pos];
        if (kind == null || hit.pos == source.pos) continue;
        final z = hit.zipf ?? r.zipf ?? 0;
        if (z > (best[kind]?.zipf ?? -1)) best[kind] = (word: w, zipf: z);
      }
      for (final e in best.entries) {
        add(e.key, e.value.word);
      }
    }
    return [
      for (final k in _formOrder)
        if (byKind.containsKey(k)) (kind: k, word: byKind[k]!),
      for (final e in byKind.entries)
        if (!_formOrder.contains(e.key)) (kind: e.key, word: e.value),
    ];
  }

  Widget? _field(BuildContext context, CardBackField field, WordLinks links,
      CardLook look) {
    switch (field) {
      case CardBackField.word:
      case CardBackField.pronunciation:
        return null; // in the header
      case CardBackField.posAndMeaning:
        final pos = activePos ?? entry.pos;
        final meaning = activeMeaning ?? entry.meaning;
        final definition = activeDefinition ?? entry.definition;
        if (template.publishedLayout != null) {
          final source =
              LexiconPack.instance.lookup(entry.word, pos: pos)?.entry;
          final meanings =
              source?.senses.where((s) => (s.native ?? '').isNotEmpty).toList();
          return _Block(
              '逐義釋義',
              _items(field, [
                if (meanings == null || meanings.isEmpty)
                  Text(meaning)
                else
                  for (final sense in meanings) Text(sense.native!),
              ], initial: 3));
        }
        // Card #251 item 2: the part of speech only — no CEFR level chip.
        // 問題回報 #469: same title as the word detail's meaning section.
        return _Block(
          '詞性與意思',
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (pos.isNotEmpty) ...[
                Row(children: [TagChip(posLabel(pos))]),
                const SizedBox(height: 6),
              ],
              Text(meaning, style: look.meaning),
              if (definition != null)
                LinkedText(definition,
                    style: MFont.manrope(14, FontWeight.w600, MColors.muted),
                    links: links,
                    onOpenWord: onOpenWord),
            ],
          ),
        );
      case CardBackField.photoContext:
        final all = photos.isNotEmpty
            ? photos
            : [if (photo case final p?) (p, anchor, photoCredit)];
        if (all.isEmpty) return null;
        // Card #251 item 3: no 「照片情境」 title and no word label over the
        // photo; item 8: swipe between the word's photos.
        var initial = all.indexWhere((o) => o.$1.id == photo?.id);
        if (initial < 0) initial = 0;
        return _PhotoPager(
            photos: all,
            initialIndex: initial,
            onSelected: onPhotoSelected,
            onAnchorMoved: (o, to) {
              final repo = AppScope.of(context).repository;
              for (final occ in repo.occurrencesOf(entry.id)) {
                if (occ.photoId == o.$1.id) {
                  repo.moveLabel(occ.id, to);
                  break;
                }
              }
            },
            height: look.photoHeight,
            radius: look.photoRadius,
            // 圖片沉浸 (#317): the word is written on the photo.
            overlay: look.photoHero ? _HeroWord(entry.word, look) : null,
            // 圖片沉浸 already writes the word on the photo.
            pinFor: AppScope.of(context).settings.showPhotoLabels &&
                    !look.photoHero
                ? (o) => o.$2 == null
                    ? null
                    : PinData(
                        id: entry.word,
                        anchor: o.$2!,
                        word: displayWord(entry.word),
                        zh: activeMeaning ?? entry.meaning)
                : null);
      case CardBackField.example:
        // Spec sections 4 and 7: 3–5 examples at the learner's level.
        final recommended = learningExamples(entry, learnerLevel,
            maxItems: 10000);
        if (recommended.isEmpty) return null;
        return _Block(
          '例句與翻譯',
          _items(field, [
            // Item 4: the sentences sit close together.
            for (final x in recommended)
              Container(
                margin: EdgeInsets.only(bottom: look.exampleGap),
                padding: look.examplePadding,
                decoration: look.example,
                child: ExampleText(
                    example: x,
                    links: links,
                    onOpenWord: onOpenWord,
                    showTranslation:
                        template.publishedLayout?['show_translation'] != false),
              ),
          ], initial: 5),
        );
      case CardBackField.formsAndDerivations:
        // 問題回報 #406: one cell per kind of form (過去式、過去分詞、現在分詞、
        // 第三人稱、複數、比較級… and the family's other parts of speech),
        // laid out in an even grid; kinds without a word are left out.
        final cells = _formCells();
        return cells.isEmpty
            ? null
            : _Block(
                '詞形變化',
                _FormGrid(cells: cells, links: links, onOpenWord: onOpenWord),
              );
      case CardBackField.related:
        // Item 6: one block per relation type, each filling the width;
        // blocks without data are left out.
        // Card #416 opened these fully; problem report #467 caps each block
        // at its first 5 words (easier first), the rest behind 顯示更多.
        // The word detail page still lists them all.
        const initial = 5;
        final blocks = <Widget>[];
        final shown = <String>{};
        for (final (label, kinds) in const [
          ('同義詞', ['synonyms']),
          ('反義詞', ['antonyms']),
          ('相關詞', ['related', 'derived_terms']),
          ('近音字', ['homophones']),
          ('容易混淆的字', ['near_homophones', 'similar_spelling']),
        ]) {
          final words = _relations(kinds, maxItems: 10000, shown: shown);
          if (words.isEmpty) continue;
          blocks.add(_Block(
            label,
            ShowMoreItems(
              initial: initial,
              wrap: true,
              children: [
                for (final w in words)
                  _WordChip(w.word,
                      meaning: w.meaning, links: links, onOpenWord: onOpenWord),
              ],
            ),
          ));
        }
        if (blocks.isEmpty) return null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final (i, b) in blocks.indexed) ...[
              if (i > 0) const SizedBox(height: 16),
              b,
            ],
          ],
        );
      case CardBackField.morphology:
        // Item 7: the admin's 構詞拆解 look — one rounded box per part,
        // joined by 「+」.
        final parts = _morphemes();
        final origin = learningEtymology(entry);
        return parts.isEmpty && origin == null
            ? null
            : _Block(
                '構詞拆解',
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (parts.isNotEmpty)
                      _MorphologyParts(
                          parts: parts, links: links, onOpenWord: onOpenWord),
                    if (parts.isNotEmpty && origin != null)
                      const SizedBox(height: 8),
                    if (origin != null)
                      Text(origin,
                          style: MFont.manrope(
                              13, FontWeight.w600, MColors.muted)),
                  ],
                ),
              );
      case CardBackField.source:
        return null; // Back cards omit provenance for every template.
      case CardBackField.learningInfo:
        return null; // Review history belongs in word details, not the answer.
    }
  }

  /// The parts of the word: the pack's, or the learner's own edit / the
  /// stored root and affixes read as prefix (ends with -), root, suffix.
  List<LexMorpheme> _morphemes() {
    List<LexMorpheme> fromText(String text) => [
          for (final raw in text.split(RegExp(r'\s*[＋+]\s*')))
            if (raw.trim().isNotEmpty)
              () {
                final m =
                    RegExp(r'^(.*?)(?:[（(](.*)[）)])?$').firstMatch(raw.trim())!;
                final part = m.group(1)!.trim();
                return LexMorpheme(
                    part,
                    part.endsWith('-')
                        ? 'prefix'
                        : part.startsWith('-')
                            ? 'suffix'
                            : 'root',
                    null,
                    m.group(2)?.trim());
              }(),
        ];
    if (entry.userEdited.contains(WordField.morphology)) {
      final parts = fromText(entry.morphology ?? '');
      return parts.length > 1 ? parts : const [];
    }
    final source = _source;
    if (source != null) {
      return source.morphemes.length > 1 ? source.morphemes : const [];
    }
    final stored = [if (entry.root != null) entry.root!, ...entry.affixes];
    return stored.length > 1 ? fromText(stored.join(' ＋ ')) : const [];
  }

  @override
  Widget build(BuildContext context) {
    final source = _source;
    final ipa =
        (entry.ipa?.trim().isNotEmpty ?? false) ? entry.ipa : source?.ipa;
    // 發音與 IPA sits in the header; switched off in 卡片背面順序, the IPA
    // and the play button go (the switch used to do nothing).
    final showPronunciation = template.backFields
        .where((f) => f.field == CardBackField.pronunciation)
        .every((f) => f.visible);
    final links = WordLinks.of(AppScope.of(context).repository);
    final look = CardLook.of(context);
    // Every visible template field that has data (spec: 可用時一併顯示；
    // 欄位沒有內容時自動省略).
    final fields = [
      for (final f in template.backFields)
        if (f.visible) _configuredField(context, f, links, look),
    ].whereType<Widget>().toList();
    // 圖片沉浸 (#317): the photo leads, the word written on it.
    final hero =
        look.photoHero ? fields.whereType<_PhotoPager>().firstOrNull : null;
    if (hero != null) fields.remove(hero);
    var panel = 0;
    Widget section(Widget w) {
      // A photo needs no panel behind it.
      final decoration = w is _PhotoPager ? null : look.sectionPanel(panel++);
      if (decoration == null) return w;
      return Container(
          decoration: decoration, padding: look.sectionPadding, child: w);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (entry.entryType != 'word') TagChip(entryTypeLabel(entry.entryType)),
        if (answerCorrect != null) ...[
          Container(
            padding: const EdgeInsets.all(MSpace.md),
            decoration: MDecor.softPanel(
              color: answerCorrect! ? MColors.successSoft : MColors.againBg,
              radius: MRadii.md,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                UiText(answerCorrect! ? '答對了' : '答錯了',
                    style: MFont.manrope(17, FontWeight.w800,
                        answerCorrect! ? MColors.success : MColors.againFg)),
                if (submittedAnswer?.isNotEmpty == true) ...[
                  const SizedBox(height: 4),
                  UiText('你的答案：${displayWord(submittedAnswer!)}',
                      style:
                          MFont.manrope(14, FontWeight.w600, MColors.gray700)),
                ],
                if (answerCorrect == false &&
                    correctAnswer?.isNotEmpty == true) ...[
                  const SizedBox(height: 2),
                  UiText('正確答案：${displayWord(correctAnswer!)}',
                      style:
                          MFont.manrope(14, FontWeight.w700, MColors.gray900)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        if (hero != null) ...[hero, const SizedBox(height: 8)],
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (hero == null)
                    // 圖片沉浸 without a photo: the headword is white (made for
                    // the dark scrim), so it needs the dark ink on the canvas.
                    Text(displayWord(entry.word),
                        style: look.photoHero
                            ? look.headword.copyWith(color: look.meaning.color)
                            : look.headword),
                  if (ipa != null && showPronunciation)
                    Text(ipa, style: look.ipa),
                ],
              ),
            ),
            if (showPronunciation) ...[
              for (final accent in const ['en-GB', 'en-US'])
                IconButton(
                  tooltip: accent == 'en-GB' ? '播放英式發音' : '播放美式發音',
                  onPressed: () => playAccent(context, entry, accent),
                  icon: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.volume_up_outlined),
                    UiText(accent == 'en-GB' ? '英式' : '美式',
                        style: MFont.caption),
                  ]),
                ),
            ],
          ],
        ),
        for (final (i, w) in fields.indexed) ...[
          SizedBox(height: look.sectionGap),
          // Only the top of the back is built in the flip frame; the rest
          // follows one frame later (問題回報 #491: a frame of 68 ms on
          // iPhone 12 when every block was built at once).
          i < _eagerBlocks ? section(w) : _DeferredBuild(child: section(w)),
        ],
      ],
    );
  }
}

const _eagerBlocks = 2;

/// Builds [child] on the frame after this one; [SizedBox.shrink] until then.
class _DeferredBuild extends StatefulWidget {
  final Widget child;
  const _DeferredBuild({required this.child});

  @override
  State<_DeferredBuild> createState() => _DeferredBuildState();
}

class _DeferredBuildState extends State<_DeferredBuild> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _ready = true);
    });
  }

  @override
  Widget build(BuildContext context) =>
      _ready ? widget.child : const SizedBox.shrink();
}

/// 詞形變化 as an even grid (問題回報 #406): equal-width cells, the kind in
/// small type above the word. A word that can be opened is underlined.
class _FormGrid extends StatelessWidget {
  final List<({String kind, String word})> cells;
  final WordLinks links;
  final ValueChanged<String>? onOpenWord;

  const _FormGrid({required this.cells, required this.links, this.onOpenWord});

  @override
  Widget build(BuildContext context) {
    final look = CardLook.of(context);
    return LayoutBuilder(builder: (context, c) {
      const gap = 8.0;
      final columns = c.maxWidth >= 420 ? 3 : 2;
      final width = (c.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final cell in cells)
            SizedBox(
              width: width,
              child: _FormCell(
                  kind: cell.kind,
                  word: cell.word,
                  links: links,
                  look: look,
                  onOpenWord: onOpenWord),
            ),
        ],
      );
    });
  }
}

class _FormCell extends StatelessWidget {
  final String kind;
  final String word;
  final WordLinks links;
  final CardLook look;
  final ValueChanged<String>? onOpenWord;

  const _FormCell(
      {required this.kind,
      required this.word,
      required this.links,
      required this.look,
      this.onOpenWord});

  @override
  Widget build(BuildContext context) {
    final id = links.idFor(word);
    return Tap(
      label: id == null ? '$kind $word' : '$kind $word，查看單字',
      onTap: id == null ? null : () => openWordLink(context, id, onOpenWord),
      child: Container(
        key: ValueKey('form-cell-$kind'),
        constraints: BoxConstraints(minHeight: look.chipMinHeight),
        padding: look.chipPadding,
        decoration: look.chip(id != null),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            UiText(kind,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: look.chipMeaning),
            const SizedBox(height: 2),
            Text(word,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: look.chipWord.copyWith(
                    decoration: id == null ? null : TextDecoration.underline,
                    decorationColor:
                        look.chipWord.color?.withValues(alpha: 0.45))),
          ],
        ),
      ),
    );
  }
}

/// A word with its meaning in one chip (forms, related words); tapping a
/// word that is in the learner's database opens it (item 9).
class _WordChip extends StatelessWidget {
  final String word;
  final String meaning;
  final WordLinks links;
  final ValueChanged<String>? onOpenWord;

  const _WordChip(this.word,
      {required this.meaning, required this.links, this.onOpenWord});

  @override
  Widget build(BuildContext context) {
    final id = links.idFor(word);
    final look = CardLook.of(context);
    return Tap(
      label: id == null ? null : '$word，查看單字',
      onTap: id == null ? null : () => openWordLink(context, id, onOpenWord),
      child: Container(
        constraints: BoxConstraints(minHeight: look.chipMinHeight),
        padding: look.chipPadding,
        decoration: look.chip(id != null),
        child: Text.rich(TextSpan(children: [
          TextSpan(
              text: word,
              style: look.chipWord.copyWith(
                  decoration: id == null ? null : TextDecoration.underline,
                  decorationColor:
                      look.chipWord.color?.withValues(alpha: 0.45))),
          if (meaning.isNotEmpty)
            TextSpan(text: '  $meaning', style: look.chipMeaning),
        ])),
      ),
    );
  }
}

/// 構詞拆解 as in the admin's word page: a rounded box per morpheme (the
/// part in bold, its kind, its native meaning with an AI mark when the AI
/// wrote it), the boxes joined by 「+」.
class _MorphologyParts extends StatelessWidget {
  final List<LexMorpheme> parts;
  final WordLinks links;
  final ValueChanged<String>? onOpenWord;

  const _MorphologyParts(
      {required this.parts, required this.links, this.onOpenWord});

  static String kindLabel(LexMorpheme m) => switch (m.kind) {
        'prefix' => '字首',
        'suffix' => '字尾',
        _ => m.free ? '單字' : '字根',
      };

  static ({Color bg, Color border}) colors(String kind) => switch (kind) {
        'prefix' => (
            bg: MColors.primarySoft,
            border: MColors.primary.withValues(alpha: 0.35)
          ),
        'suffix' => (
            bg: MColors.hardBg,
            border: MColors.hardFg.withValues(alpha: 0.35)
          ),
        _ => (
            bg: MColors.successSoft,
            border: MColors.success.withValues(alpha: 0.4)
          ),
      };

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 6,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final (i, m) in parts.indexed) ...[
            if (i > 0)
              Text('+',
                  style: MFont.manrope(16, FontWeight.w800, MColors.muted)),
            _MorphemeBox(m, links: links, onOpenWord: onOpenWord),
          ],
        ],
      );
}

class _MorphemeBox extends StatelessWidget {
  final LexMorpheme m;
  final WordLinks links;
  final ValueChanged<String>? onOpenWord;

  const _MorphemeBox(this.m, {required this.links, this.onOpenWord});

  @override
  Widget build(BuildContext context) {
    final c = _MorphologyParts.colors(m.kind);
    final native = (m.native ?? '').trim();
    final id = links.idFor(m.part.replaceAll('-', ''));
    return Tap(
      label: id == null ? null : '${m.part}，查看單字',
      onTap: id == null ? null : () => openWordLink(context, id, onOpenWord),
      child: Container(
        constraints: const BoxConstraints(minWidth: 72),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: c.bg,
          borderRadius: BorderRadius.circular(MRadii.xs),
          border: Border.all(color: c.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(m.part,
                style: MFont.manrope(18, FontWeight.w800, MColors.ink).copyWith(
                    decoration: id == null ? null : TextDecoration.underline,
                    decorationColor: MColors.primary.withValues(alpha: 0.45))),
            UiText(_MorphologyParts.kindLabel(m),
                style: MFont.manrope(11, FontWeight.w600, MColors.muted)),
            if (native.isNotEmpty)
              Row(mainAxisSize: MainAxisSize.min, children: [
                Text(native,
                    style: MFont.manrope(13, FontWeight.w700, MColors.ink)),
                if (m.nativeAi) ...[
                  const SizedBox(width: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                    decoration: BoxDecoration(
                        color: MColors.primary,
                        borderRadius: BorderRadius.circular(4)),
                    child: Text('AI',
                        style: MFont.manrope(9, FontWeight.w800, Colors.white)),
                  ),
                ],
              ]),
          ],
        ),
      ),
    );
  }
}

/// A dot where the word is in the photo, without its label (item 3).
class _AnchorDot extends StatelessWidget {
  final Photo photo;
  final LabelPoint anchor;

  /// Set when the learner may correct the spot (問題回報 #410): long-press
  /// the dot and drag it.
  final ValueChanged<LabelPoint>? onMoved;

  const _AnchorDot({required this.photo, required this.anchor, this.onMoved});

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final geo = CoverGeometry(Size(c.maxWidth, c.maxHeight), photo);
        final at = geo.toBox(anchor);
        if (onMoved != null) {
          return Stack(children: [
            DraggableAnchorDot(
                key: const ValueKey('back-anchor-dot'),
                at: at,
                onMoved: (to) => onMoved!(geo.fromBox(to))),
          ]);
        }
        return IgnorePointer(
          child: Stack(children: [
            Positioned(
              left: at.dx - 7,
              top: at.dy - 7,
              child: Container(
                key: const ValueKey('back-anchor-dot'),
                width: 14,
                height: 14,
                decoration: BoxDecoration(
                  color: MColors.primary,
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 2.5),
                  boxShadow: MShadows.soft,
                ),
              ),
            ),
          ]),
        );
      });
}

/// The word's photos, swiped left and right (card #251 item 8), each
/// without a word label (item 3); long-press shows a pack picture's
/// author / license.
class _PhotoPager extends StatefulWidget {
  final List<CardPhoto> photos;
  final int initialIndex;
  final ValueChanged<int>? onSelected;
  final double height;
  final double radius;

  /// Drawn over the photo, not swiped with it; taps pass through.
  final Widget? overlay;

  /// The word's label on the photo (設定 → 照片上的單字標示).
  final PinData? Function(CardPhoto photo)? pinFor;

  /// The learner dragged the word's dot on [photo] to a new spot.
  final void Function(CardPhoto photo, LabelPoint to)? onAnchorMoved;

  const _PhotoPager(
      {this.onAnchorMoved,
      required this.photos,
      required this.initialIndex,
      this.onSelected,
      this.height = 200,
      this.radius = 16,
      this.overlay,
      this.pinFor});

  @override
  State<_PhotoPager> createState() => _PhotoPagerState();
}

class _PhotoPagerState extends State<_PhotoPager> {
  /// Above this many photos the page dots switch to a "第 N / M 張" counter.
  static const _maxDotPhotos = 12;

  late final PageController _controller =
      PageController(initialPage: widget.initialIndex);
  late int _index = widget.initialIndex;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Widget _photo(BuildContext context, CardPhoto o) {
    final p = o.$1;
    final a = o.$2;
    final photoWidget = PinnedPhoto(
      photo: p,
      radius: widget.radius,
      imageErrorBuilder: p.networkUrl == null
          ? null
          : (_) => const Center(child: UiText('圖片暫時無法載入，稍後再試')),
      // No word label on the photo (item 3); the word's spot is still
      // marked with a dot so the learner sees where it was.
      pins: [if (widget.pinFor?.call(o) case final pin?) pin],
      overlay: a == null || widget.pinFor?.call(o) != null
          ? null
          : _AnchorDot(
              photo: p,
              anchor: a,
              onMoved: widget.onAnchorMoved == null
                  ? null
                  : (to) => widget.onAnchorMoved!(o, to)),
    );
    final credit = o.$3?.trim();
    if (credit == null || credit.isEmpty) return photoWidget;
    return GestureDetector(
      onLongPress: () {
        showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const UiText('圖片來源'),
            content: Text(credit),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const UiText('關閉'),
              ),
            ],
          ),
        );
      },
      child: photoWidget,
    );
  }

  @override
  Widget build(BuildContext context) {
    final photos = widget.photos;
    Widget framed(Widget photo) => SizedBox(
          height: widget.height,
          child: widget.overlay == null
              ? photo
              : Stack(fit: StackFit.expand, children: [
                  photo,
                  IgnorePointer(
                      child: ClipRRect(
                          borderRadius: BorderRadius.circular(widget.radius),
                          child: widget.overlay)),
                ]),
        );
    if (photos.length == 1) return framed(_photo(context, photos.single));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        framed(
          PageView.builder(
            controller: _controller,
            itemCount: photos.length,
            onPageChanged: (i) {
              setState(() => _index = i);
              widget.onSelected?.call(i);
            },
            itemBuilder: (context, i) => Padding(
              padding: EdgeInsets.only(
                  left: i == 0 ? 0 : 4, right: i == photos.length - 1 ? 0 : 4),
              child: _photo(context, photos[i]),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Semantics(
          label: '第 ${_index + 1} 張，共 ${photos.length} 張，左右滑動切換照片',
          child: photos.length > _maxDotPhotos
              // Too many dots overflow a 350px phone row (card #308), so
              // a counter replaces them.
              ? Center(
                  child: UiText(
                    '第 ${_index + 1} / ${photos.length} 張　·　左右滑動換照片',
                    style: MFont.manrope(13, FontWeight.w600, MColors.muted),
                  ),
                )
              : Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var i = 0; i < photos.length; i++)
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: i == _index ? 16 : 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: i == _index ? MColors.primary : MColors.border,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

/// 圖片沉浸 (#317): the word in white on a dark fade at the photo's foot.
/// The fade reaches 70% black under the text, so it keeps ≥ 4.5:1 on any
/// photo.
class _HeroWord extends StatelessWidget {
  final String word;
  final CardLook look;

  const _HeroWord(this.word, this.look);

  @override
  Widget build(BuildContext context) => Container(
        alignment: Alignment.bottomLeft,
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            stops: [0.45, 1],
            colors: [Color(0x00000000), Color(0xB3000000)],
          ),
        ),
        child: Text(displayWord(word),
            key: const ValueKey('hero-word'),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: look.headword),
      );
}
