import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show AssetBundle, rootBundle;

import '../models/word_candidate.dart';
import '../models/card_template.dart';
import '../models/word_detail.dart';
import '../models/word_entry.dart';
import 'learning_content.dart' show formLabel, posLabel;

/// The downloaded language pack (spec section 08, 資料比對階段): one
/// direction (target → native) exported by the lexicon admin as
/// `assets/lexicon/{target}-{native}.json` — the same rows and stable
/// lexeme ids as the SQLite package.
///
/// Recognized words are looked up here, never online: target language +
/// normalized lemma + part of speech first, then the lemma alone, then
/// the forms table (apples → apple).
class LexiconPack extends ChangeNotifier {
  LexiconPack();

  static final LexiconPack instance = LexiconPack();

  String? target;
  String? native;
  String? version;
  String? mediaBase;
  CardTemplate? cardTemplate;
  bool hasCatalog = false;
  List<Map<String, dynamic>> catalogImages = [];
  List<LexEntry> get catalogWords => _byId.values.toList(growable: false);
  final Map<int, LexEntry> _byId = {};
  final Map<String, List<LexEntry>> _byLemma = {};
  final Map<String, List<LexEntry>> _byForm = {};
  // Forms that share a word's card, by that word (tether: tethered).
  final Map<String, List<LexEntry>> _family = {};
  final Map<int, int> _redirects = {};
  final Map<String, String> labels = {};

  /// Words recognized in photos that the pack doesn't have yet
  /// (missing_lexeme_requests) or has without native text
  /// (missing_localization_requests), for the admin to fill.
  final Map<String, MissingRequest> requests = {};

  bool get isEmpty => _byLemma.isEmpty;
  int get size => _byId.values.where((e) => e.full).length;

  static String assetFor(String target, String native) =>
      'assets/lexicon/$target-$native.json';

  /// Loads the pack for this direction; an app without one simply links
  /// nothing (every word becomes a missing-word request).
  Future<void> load(
      {required String target,
      required String native,
      AssetBundle? bundle}) async {
    if (this.target == target && this.native == native && !isEmpty) return;
    try {
      final raw =
          await (bundle ?? rootBundle).loadString(assetFor(target, native));
      // The bundled pack is tens of MB (問題回報 #265): parse it off the
      // UI thread (compute runs inline on the web).
      loadJson(await compute(jsonDecode, raw) as Map<String, dynamic>);
    } catch (e) {
      debugPrint('No language pack for $target-$native: $e');
      clear();
    }
    this.target = target;
    this.native = native;
    notifyListeners();
  }

  void clear() {
    _byId.clear();
    _byLemma.clear();
    _byForm.clear();
    _family.clear();
    _redirects.clear();
    labels.clear();
    version = null;
    mediaBase = null;
    cardTemplate = null;
    hasCatalog = false;
    catalogImages = [];
  }

  void loadJson(Map<String, dynamic> j) {
    final template = j['card_template'] == null
        ? null
        : CardTemplate.fromPublished(
            j['card_template'] as Map<String, dynamic>);
    clear();
    cardTemplate = template;
    target = j['target_language'] as String?;
    native = j['native_language'] as String?;
    version = j['created_at'] as String?;
    mediaBase = j['media_base'] as String?;
    hasCatalog = j['catalog_version'] == 1;
    catalogImages = [
      for (final image in (j['catalog_images'] as List? ?? []))
        Map<String, dynamic>.from(image as Map)
    ];
    (j['labels'] as Map? ?? {}).forEach((k, v) => labels['$k'] = '$v');
    (j['redirects'] as Map? ?? {})
        .forEach((k, v) => _redirects[int.parse('$k')] = (v as num).toInt());
    // 問題回報 #191: an inflected form (tore) is a pointer to its lemma
    // (tear), not a card: its id resolves to the lemma, its spelling finds it.
    final pointers = <String, int>{};
    for (final raw in (j['lexemes'] as List? ?? const [])) {
      final to = (raw as Map)['redirect_to'];
      if (to is num) {
        _redirects[(raw['id'] as num).toInt()] = to.toInt();
        pointers['${raw['normalized']}'] = to.toInt();
        continue;
      }
      final e = LexEntry.fromJson(raw as Map<String, dynamic>);
      _byId[e.id] = e;
      if (!e.full) continue;
      _byLemma.putIfAbsent(e.normalized, () => []).add(e);
      for (final f in e.forms) {
        _byForm.putIfAbsent(f.normalized, () => []).add(e);
      }
      if (e.card != null) _family.putIfAbsent(e.card!, () => []).add(e);
    }
    pointers.forEach((form, id) {
      final base = _byId[id];
      if (base == null || !base.full) return;
      final list = _byForm.putIfAbsent(form, () => []);
      if (!list.contains(base)) list.add(base);
    });
    notifyListeners();
  }

  /// Install an already validated pack without parsing every entry twice.
  void replaceWith(LexiconPack candidate) {
    clear();
    target = candidate.target;
    native = candidate.native;
    version = candidate.version;
    mediaBase = candidate.mediaBase;
    cardTemplate = candidate.cardTemplate;
    hasCatalog = candidate.hasCatalog;
    catalogImages = candidate.catalogImages;
    labels.addAll(candidate.labels);
    _byId.addAll(candidate._byId);
    _byLemma.addAll(candidate._byLemma);
    _byForm.addAll(candidate._byForm);
    _family.addAll(candidate._family);
    _redirects.addAll(candidate._redirects);
    notifyListeners();
  }

  List<LexemeUsage> usagesFor(String word) => [
        for (final e in _byLemma[normalize(word)] ?? const <LexEntry>[])
          LexemeUsage(
              id: 'pack:$target:${e.id}',
              pos: shortPos(e.pos),
              senses: [
                for (final s in e.senses)
                  WordSense(
                      id: 'pack:$target:${s.id}',
                      meaning: s.native ?? '',
                      definition: s.definition)
              ],
              examples: [
                for (final x in e.examples)
                  WordExample(
                      text: x.text,
                      translation: x.translation,
                      senseId: x.senseId == null
                          ? null
                          : 'pack:$target:${x.senseId}',
                      source: x.source,
                      difficulty: x.difficulty,
                      aiGenerated: x.aiGenerated,
                      aiTranslated: x.translationAi)
              ]),
      ];

  LexEntry? byId(int id) => _byId[_redirects[id] ?? id];

  /// Every part of speech stored for one spelling, for the full dictionary
  /// detail page. The returned list cannot mutate the loaded pack.
  List<LexEntry> entriesFor(String word) =>
      List.unmodifiable(_byLemma[normalize(word)] ?? const <LexEntry>[]);

  /// The entry for a recognized word, or null. [pos] is the app's
  /// part of speech (noun, verb, adj., adv., phrase). A form that shares
  /// its word's card (tethered → tether, 問題回報 #51) gives that word,
  /// via 'family'.
  LexiconHit? lookup(String word, {String? pos}) {
    final hit = _lookup(word, pos: pos);
    final base = _byLemma[hit?.entry.card];
    if (hit == null || base == null || base.isEmpty) return hit;
    return LexiconHit(_prefer(base, pos).first, 'family');
  }

  static List<LexEntry> _prefer(List<LexEntry> list, String? pos) {
    if (pos == null) return list;
    final p = packPos(pos);
    return [...list.where((e) => e.pos == p), ...list.where((e) => e.pos != p)];
  }

  /// The forms that share [e]'s card (tethered, for tether).
  List<LexEntry> familyOf(LexEntry e) => _family[e.normalized] ?? const [];

  /// [e] as the app's [WordDetail], with the meanings of the forms that
  /// share its card.
  WordDetail detailFor(LexEntry e) => e.toDetail(family: familyOf(e));

  LexiconHit? _lookup(String word, {String? pos}) {
    final w = normalize(word);
    final p = pos == null ? null : packPos(pos);
    List<LexEntry> prefer(List<LexEntry> list) => _prefer(list, pos);
    final exact = _byLemma[w];
    final viaForm = _byForm[w];
    if (exact != null && exact.isNotEmpty) {
      final best = prefer(exact).first;
      if (p != null && best.pos != p) {
        // A dog lying on the grass is lie the verb, not lying 說謊的: the
        // form of a word with that part of speech wins (問題回報 #51).
        final form = viaForm?.where((e) => e.pos == p).firstOrNull;
        if (form != null) return LexiconHit(form, 'form');
      }
      return LexiconHit(
          best, best.pos == p || p == null ? 'lemma+pos' : 'lemma');
    }
    if (viaForm != null && viaForm.isNotEmpty) {
      return LexiconHit(prefer(viaForm).first, 'form');
    }
    return null;
  }

  /// A recognized candidate linked to the pack: lemma (inflected forms
  /// looked up through the forms table), native meaning and lexeme id.
  /// Words the pack lacks are recorded as missing-word requests.
  WordCandidate link(WordCandidate c) {
    final hit = lookup(c.word, pos: c.pos);
    if (hit == null) {
      _request('missing_lexeme', c.word, c.pos);
      return c.lexemeId == null ? c : c.copyWith(lexemeId: () => null);
    }
    final e = hit.entry;
    final meaning = e.learnerMeaning;
    if (meaning == null) {
      _request('missing_localization', e.lemma, e.pos, lexemeId: e.id);
    }
    return c.copyWith(
      word: hit.via == 'form' || hit.via == 'family' ? e.normalized : null,
      meaning: meaning ?? (c.meaning.isEmpty ? null : c.meaning),
      lexemeId: () => e.id,
    );
  }

  List<WordCandidate> linkAll(List<WordCandidate> cs) =>
      [for (final c in cs) link(c)];

  /// The pack entry as the app's [WordDetail], for new word entries.
  WordDetail? detail(String word) {
    final e = lookup(word)?.entry;
    return e == null ? null : detailFor(e);
  }

  void _request(String kind, String lemma, String pos, {int? lexemeId}) {
    final key = '$kind:${normalize(lemma)}:$pos';
    final r = requests[key];
    requests[key] = MissingRequest(
      kind: kind,
      lemma: normalize(lemma),
      pos: pos,
      lexemeId: lexemeId,
      target: target,
      native: native,
      count: (r?.count ?? 0) + 1,
    );
  }

  static String normalize(String word) =>
      word.trim().toLowerCase().replaceAll('’', "'");

  /// App part of speech → pack part of speech.
  static String packPos(String pos) =>
      switch (pos.replaceAll('.', '').toLowerCase()) {
        'adjective' => 'adj',
        'adverb' => 'adv',
        final p => p,
      };
}

class LexiconHit {
  final LexEntry entry;

  /// lemma+pos, lemma, or form (an inflected form led to the lemma).
  final String via;

  const LexiconHit(this.entry, this.via);
}

class MissingRequest {
  final String kind; // missing_lexeme / missing_localization
  final String lemma;
  final String pos;
  final int? lexemeId;
  final String? target;
  final String? native;
  final int count;

  const MissingRequest({
    required this.kind,
    required this.lemma,
    required this.pos,
    this.lexemeId,
    this.target,
    this.native,
    this.count = 1,
  });

  Map<String, dynamic> toJson() => {
        'kind': kind,
        'lemma': lemma,
        'pos': pos,
        'lexeme_id': lexemeId,
        'target_language': target,
        'native_language': native,
        'count': count,
      };
}

class LexSense {
  final int id;
  final String definition;
  final String? native;
  final bool nativeAi;
  final String? register;

  /// Usage labels from the dictionary (obsolete, slang, informal…).
  final List<String> labels;

  const LexSense(this.id, this.definition, this.native, this.nativeAi,
      {this.register, this.labels = const []});
}

class LexForm {
  final String field;
  final String form;
  final String normalized;
  final String? label;

  const LexForm(this.field, this.form, this.normalized, this.label);
}

class LexMorpheme {
  final String part;
  final String kind; // prefix / root / suffix
  final String? meaning;
  final String? native;

  /// A root that is a word on its own (flap in flapping): 單字, not 字根.
  final bool free;

  /// [native] was written by the AI (shown with an AI mark, as in the admin).
  final bool nativeAi;

  const LexMorpheme(this.part, this.kind, this.meaning, this.native,
      {this.free = false, this.nativeAi = false});
}

class LexRelation {
  final String relation;
  final String word;
  final int? lexemeId;
  final String? native;
  final String? cefr;
  final double? zipf;
  final String? rarity;
  final bool hideByDefault;

  const LexRelation(this.relation, this.word, this.lexemeId, this.native,
      {this.cefr, this.zipf, this.rarity, this.hideByDefault = false});
}

class LexExample {
  final String text;
  final String? translation;
  final bool translationAi;
  final String? source;
  final String? difficulty;

  /// The sense the sentence was bound to, when the pack says.
  final int? senseId;

  const LexExample(this.text, this.translation, this.translationAi, this.source,
      this.difficulty,
      {this.senseId});

  /// The sentence itself was written by AI (a CEFR level the dictionaries
  /// left short), not only its translation.
  bool get aiGenerated => source == 'ai_translate';
}

/// Where the word comes from (Wiktionary), with its native-language text
/// when the admin has one.
class LexEtymology {
  final String text;
  final String? native;
  final String? originLanguage;
  final String? originalForm;

  const LexEtymology(this.text, this.native,
      {this.originLanguage, this.originalForm});
}

class LexEntry {
  final String entryType;
  final int id;
  final String lemma;
  final String normalized;
  final String pos;
  final String status;
  final String? cefr;
  final double? zipf;
  final List<LexSense> senses;
  final List<LexForm> forms;
  final String? ipa;
  final String? audio; // relative to assets/lexicon/media/
  final List<({String path, String? accent})> recordings;
  final List<LexExample> examples;
  final List<LexRelation> relations;
  final List<LexMorpheme> morphemes;
  final LexEtymology? etymology;
  final Map<String, String> missing;

  /// A rarer part of speech of a spelling (問題回報 #16): its CEFR is a
  /// frequency estimate and database lists put it after the main usages.
  final bool rareUsage;

  /// [cefr] is a frequency estimate, not from the CEFR-J / Octanove lists:
  /// shown as 「估算」 (問題回報 #139 decision, #132).
  final bool cefrEstimated;

  /// The word whose card this form shares (tethered: tether), or null
  /// (owner decision 2026-10-14, 問題回報 #51).
  final String? card;

  /// This part of speech is only [card]'s form (dried the verb), so it adds
  /// no meaning to that card; dried the adjective (乾燥的) does.
  final bool cardForm;

  /// Lexeme ids whose pictures this entry shows (picture_need). Null on a
  /// pack built before that field: show this entry's own tags. Empty: this
  /// part of speech has no noun picture to share.
  final List<int>? pictureIds;

  const LexEntry({
    this.entryType = 'word',
    required this.id,
    required this.lemma,
    required this.normalized,
    required this.pos,
    required this.status,
    this.cefr,
    this.zipf,
    this.senses = const [],
    this.forms = const [],
    this.ipa,
    this.audio,
    this.recordings = const [],
    this.examples = const [],
    this.relations = const [],
    this.morphemes = const [],
    this.etymology,
    this.missing = const {},
    this.rareUsage = false,
    this.cefrEstimated = false,
    this.card,
    this.cardForm = false,
    this.pictureIds,
  });

  bool get full => status == 'full';

  /// The native meaning shown on labels: the first sense that has one.
  String? get nativeMeaning => senses
      .map((s) => s.native)
      .firstWhere((t) => (t ?? '').isNotEmpty, orElse: () => null);

  static const _rareLabels = {
    'obsolete',
    'archaic',
    'dated',
    'rare',
    'slang',
    'humorous',
    'nonstandard',
    'historical',
    'vulgar',
    'derogatory',
    'offensive',
    'euphemistic',
    'poetic',
    // Quality rules (#184): senses ranked low by lexicon/backend/app/quality.py.
    'low_priority',
  };

  /// What a learner recalls from (問題回報 #18, owner decision 2026-10-01):
  /// the Chinese of the first two common senses, skipping obsolete, slang
  /// and similar ones, each word once — tea → 茶樹；茶葉、茶、茶水.
  ///
  /// Owner decision 問題回報 #84: senses with a dictionary translation come
  /// first; an AI-filled one (often a description of a sub-sense: door
  /// 「有門的建築物」) only when no dictionary translation is left.
  /// Computed once per entry (the 資料庫單字本 filters 30k entries on every
  /// keystroke — 問題回報 #141); an entry never changes after loading.
  static final _learnerCache = Expando<Object>('learnerMeaning');
  static final _searchCache = Expando<String>('searchText');
  static const _noMeaning = Object();

  String? get learnerMeaning {
    final cached = _learnerCache[this];
    if (cached != null) {
      return identical(cached, _noMeaning) ? null : cached as String;
    }
    final value = _learnerMeaning();
    _learnerCache[this] = value ?? _noMeaning;
    return value;
  }

  /// The headword and its meaning, lower case, for search boxes.
  String get searchText =>
      _searchCache[this] ??= '$lemma ${learnerMeaning ?? ''}'.toLowerCase();

  String? _learnerMeaning() {
    final usable = senses
        .where((s) =>
            (s.native ?? '').trim().isNotEmpty &&
            !s.labels.any((l) =>
                _rareLabels.contains(l.toLowerCase()) ||
                // Another etymology: a different word with the same spelling.
                l.startsWith('etymology-')))
        .toList();
    final dictionary = usable.where((s) => !s.nativeAi).toList();
    final common =
        (dictionary.isNotEmpty ? dictionary : usable).take(2).toList();
    if (common.isEmpty) return nativeMeaning;
    final seen = <String>{};
    // A meaning that spells the answer gives it away on the front (問題回報
    // #118: toll 「徵收 toll」).
    final answer = RegExp(
        '(?<![A-Za-z])(${[
          lemma,
          ...forms.map((f) => f.form)
        ].map(RegExp.escape).join('|')})(?![A-Za-z])',
        caseSensitive: false);
    final parts = [
      for (final sense in common)
        [
          for (final word in sense.native!.split(RegExp(r'[、，,]')))
            if (word.trim().isNotEmpty &&
                !answer.hasMatch(word) &&
                seen.add(word.trim()))
              word.trim()
        ].join('、'),
    ].where((part) => part.isNotEmpty);
    return parts.isEmpty ? null : parts.join('；');
  }

  /// 構詞拆解 as one line: ex- + -ter + -ior.
  String get breakdown => morphemes.map((m) => m.part).join(' + ');

  factory LexEntry.fromJson(Map<String, dynamic> j) {
    List<Map<String, dynamic>> list(String k) => [
          for (final x in (j[k] as List? ?? const [])) x as Map<String, dynamic>
        ];
    final prons = list('pronunciations');
    final ipa = prons.where((p) => p['kind'] == 'ipa').firstOrNull;
    final audio = prons
        .where((p) => p['kind'] == 'audio' && p['audio'] != null)
        .toList()
      ..sort((a, b) =>
          (b['default'] == true ? 1 : 0) - (a['default'] == true ? 1 : 0));
    final ety = j['etymology'] as Map<String, dynamic>?;
    final etyText = (ety?['text'] as String? ?? '').trim();
    final etyNative = (ety?['native'] as String? ?? '').trim();
    return LexEntry(
      id: (j['id'] as num).toInt(),
      lemma: j['lemma'] as String,
      entryType: j['entry_type'] as String? ?? 'word',
      normalized: j['normalized'] as String,
      pos: j['pos'] as String,
      status: j['status'] as String? ?? 'full',
      cefr: j['cefr'] as String?,
      cefrEstimated: j['cefr_source'] == 'frequency_estimate' ||
          j['cefr_source'] == 'estimate',
      card: j['card'] as String?,
      cardForm: j['card_form'] == true,
      zipf: (j['zipf'] as num?)?.toDouble(),
      senses: [
        for (final s in list('senses'))
          LexSense((s['id'] as num).toInt(), s['definition'] as String? ?? '',
              s['native'] as String?, s['native_ai'] == true,
              register: s['register'] as String?,
              labels: [
                for (final l in (s['labels'] as List? ?? const [])) '$l'
              ]),
      ],
      forms: [
        for (final f in list('forms'))
          LexForm(f['field'] as String, f['form'] as String,
              f['normalized'] as String? ?? '', f['label'] as String?),
      ],
      ipa: ipa?['value'] as String?,
      audio: audio.firstOrNull?['audio'] as String?,
      recordings: [
        for (final p in audio)
          if ((p['audio'] as String).isNotEmpty)
            (path: p['audio'] as String, accent: p['accent'] as String?),
      ],
      examples: [
        for (final e in list('examples'))
          LexExample(
              e['text'] as String,
              e['translation'] as String?,
              e['translation_ai'] == true,
              e['source'] as String?,
              (e['level'] ?? e['difficulty']) as String?,
              senseId: (e['sense_id'] as num?)?.toInt()),
      ],
      relations: [
        for (final r in list('relations'))
          LexRelation(r['relation'] as String, r['word'] as String,
              (r['lexeme_id'] as num?)?.toInt(), r['native'] as String?,
              cefr: r['cefr'] as String?,
              zipf: (r['zipf'] as num?)?.toDouble(),
              rarity: r['rarity'] as String?,
              hideByDefault: r['hide_by_default'] == true),
      ],
      morphemes: [
        for (final m in list('morphemes'))
          LexMorpheme(m['part'] as String, m['kind'] as String,
              m['meaning'] as String?, m['native'] as String?,
              free: m['free'] == true, nativeAi: m['native_ai'] == true),
      ],
      etymology: etyText.isEmpty && etyNative.isEmpty
          ? null
          : LexEtymology(etyText, etyNative.isEmpty ? null : etyNative,
              originLanguage: ety?['origin_language'] as String?,
              originalForm: ety?['original_form'] as String?),
      missing: {
        for (final e in (j['missing'] as Map? ?? {}).entries)
          '${e.key}': '${e.value}',
      },
      rareUsage: j['rare_usage'] == true,
      pictureIds: j.containsKey('picture_ids')
          ? [
              for (final id in (j['picture_ids'] as List? ?? const []))
                (id as num).toInt()
            ]
          : null,
    );
  }

  static const _relationFields = {
    'synonyms': 'synonyms',
    'homophones': 'homophones',
    'near_homophones': 'homophones',
    'similar_spelling': 'similarSpelling',
  };

  /// The app's [WordDetail]. [family] are the forms sharing this card:
  /// each one's own meaning joins its form, listed first —
  /// tethered（過去分詞・形容詞：被拴住的）.
  WordDetail toDetail({List<LexEntry> family = const []}) {
    List<String> rel(String appField) => [
          for (final r in relations)
            if (_relationFields[r.relation] == appField) r.word,
        ];
    final ownMeaning = <String, List<String>>{};
    final formOf = <String, LexEntry>{};
    for (final m in family) {
      final meaning = m.learnerMeaning;
      if (meaning == null || m.cardForm) continue;
      formOf.putIfAbsent(m.normalized, () => m);
      (ownMeaning[m.normalized] ??= []).add('${posLabel(m.pos)}：$meaning');
    }
    final listed = {for (final f in forms) f.normalized};
    return WordDetail(
      word: normalized,
      definitions: [
        for (final s in senses)
          Definition(pos: pos, gloss: s.definition, register: s.register)
      ],
      definitionsSource: 'lexicon',
      ipa: ipa,
      ipaSource: ipa == null ? null : 'lexicon',
      wordAudioUrl: audio == null ? null : 'assets/lexicon/media/$audio',
      wordAudioSource: audio == null ? null : 'lexicon',
      synonyms: rel('synonyms'),
      homophones: rel('homophones'),
      similarSpelling: rel('similarSpelling'),
      inflections: [
        for (final f in [
          ...forms.where((f) => ownMeaning.containsKey(f.normalized)),
          ...forms.where((f) => !ownMeaning.containsKey(f.normalized)),
        ])
          Inflection(
              form: f.form,
              label: ownMeaning[f.normalized] == null
                  ? f.label ?? f.field
                  : '${formLabel(f.label ?? f.field)}・'
                      '${ownMeaning[f.normalized]!.join('；')}'),
        for (final MapEntry(:key, :value) in ownMeaning.entries)
          if (!listed.contains(key))
            Inflection(form: formOf[key]!.lemma, label: value.join('；')),
      ],
      derivations: [
        for (final r in relations)
          if (r.relation == 'derived_terms') Derivation(word: r.word),
      ],
      root: morphemes
          .where((m) => m.kind == 'root')
          .map((m) => m.part)
          .firstOrNull,
      affixes: [
        for (final m in morphemes)
          if (m.kind != 'root') m.part,
      ],
      morphologySource: morphemes.isEmpty ? null : 'lexicon',
      morphology: morphemes.length < 2
          ? null
          : morphemes
              .map((m) => (m.native ?? '').trim().isEmpty
                  ? m.part
                  : '${m.part}（${m.native!.split(RegExp('[、；]')).first}）')
              .join(' ＋ '),
      etymology: etymology?.native,
      exampleSentences: [
        for (final e in examples)
          ExampleSentence(
              en: e.text,
              zh: e.translation,
              source: e.source,
              zhSource: e.translationAi ? 'ai_translate' : null,
              difficulty: e.difficulty),
      ],
      relations: [
        for (final r in relations)
          RelatedTerm(
              native: r.native,
              word: r.word,
              relation: r.relation,
              cefr: r.cefr,
              zipf: r.zipf,
              rarity: r.rarity,
              hideByDefault: r.hideByDefault),
      ],
    );
  }
}
