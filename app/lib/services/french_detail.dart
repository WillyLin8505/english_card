// Card #1220 / 問題回報 #1672: what a French word's detail page shows, worked
// out from the pack's forms (LexForm.field codes such as fr_present_1s).
// Pure Dart: no widgets, so the tables are tested without a screen.
//
// Field codes read (a code the pack does not carry yet simply leaves its
// block out; card #1671 adds the missing ones):
//   fr_gender m|f|m/f|pl · fr_plural · fr_feminine · fr_feminine_plural
//   fr_masculine_before_vowel (bel) · fr_h_aspire (1/true = aspiré, 0 = muet)
//   fr_auxiliary avoir|être|avoir/être · fr_pronominal · fr_group 1|2|3|irregular
//   fr_past_participle · fr_present_participle
//   fr_<tense>_<person>, tense = present imperfect future conditional
//   subjunctive imperative simple_past pluperfect, person = 1s 2s 3s 1p 2p 3p
import 'lexicon_pack.dart';

const frenchPersons = ['1s', '2s', '3s', '1p', '2p', '3p'];
const frenchPronouns = {
  '1s': 'je',
  '2s': 'tu',
  '3s': 'il／elle',
  '1p': 'nous',
  '2p': 'vous',
  '3p': 'ils／elles',
};
const _reflexive = {
  '1s': 'me',
  '2s': 'te',
  '3s': 'se',
  '1p': 'nous',
  '2p': 'vous',
  '3p': 'se',
};

/// The moods and tenses in the order shown; [common] ones open first, the
/// rest wait behind 「顯示更多時態」. [label] is a zh UI key (ui_catalog).
class FrenchTense {
  final String code;
  final String label;
  final bool common;
  const FrenchTense(this.code, this.label, {this.common = false});
}

const frenchTenses = [
  FrenchTense('present', '現在式', common: true),
  FrenchTense('passe_compose', '複合過去式', common: true),
  FrenchTense('imperfect', '未完成過去式', common: true),
  FrenchTense('future', '簡單將來式', common: true),
  FrenchTense('conditional', '條件式'),
  FrenchTense('subjunctive', '虛擬式'),
  FrenchTense('imperative', '命令式'),
  FrenchTense('simple_past', '簡單過去式'),
  FrenchTense('pluperfect', '愈過去式'),
];

const _avoir = {
  '1s': 'ai',
  '2s': 'as',
  '3s': 'a',
  '1p': 'avons',
  '2p': 'avez',
  '3p': 'ont'
};
const _etre = {
  '1s': 'suis',
  '2s': 'es',
  '3s': 'est',
  '1p': 'sommes',
  '2p': 'êtes',
  '3p': 'sont'
};

final _vowelStart = RegExp(r'^[aeiouyhàâäéèêëîïôöùûüœæ]', caseSensitive: false);

/// One cell of a conjugation: the pronoun, the form as written (with the
/// pronoun and auxiliary joined where the tense needs them) and whether it
/// departs from the regular pattern of the verb's ending.
class FrenchCell {
  final String pronoun;
  final String text;
  final bool irregular;
  const FrenchCell(this.pronoun, this.text, {this.irregular = false});
}

class FrenchTenseTable {
  final FrenchTense tense;
  final List<FrenchCell> cells;
  const FrenchTenseTable(this.tense, this.cells);
}

class FrenchVerb {
  final String lemma;
  final String? group; // '-er' '-ir' '-re' or null
  final bool irregular;
  final List<String> auxiliaries; // avoir / être
  final bool pronominal;
  final String? pastParticiple;
  final String? presentParticiple;
  final List<FrenchTenseTable> tables;
  const FrenchVerb({
    required this.lemma,
    required this.group,
    required this.irregular,
    required this.auxiliaries,
    required this.pronominal,
    required this.pastParticiple,
    required this.presentParticiple,
    required this.tables,
  });

  List<FrenchTenseTable> get common => [
        for (final t in tables)
          if (t.tense.common) t
      ];
  List<FrenchTenseTable> get more => [
        for (final t in tables)
          if (!t.tense.common) t
      ];
}

Map<String, String> _byField(Iterable<LexForm> forms) {
  final out = <String, String>{};
  for (final f in forms) {
    out.putIfAbsent(f.field, () => f.form);
  }
  return out;
}

String _normaliseAux(String raw) {
  final v = raw.toLowerCase().replaceAll('ê', 'e');
  final avoir = v.contains('avoir');
  final etre = v.contains('etre');
  if (avoir && etre) return 'avoir/être';
  return etre ? 'être' : 'avoir';
}

/// je → j' before a vowel or mute h; the reflexive pronoun elides alike.
String _joinSubject(String person, String form, bool pronominal) {
  var rest = form;
  if (pronominal) {
    final me = _reflexive[person]!;
    final elide = _vowelStart.hasMatch(rest) &&
        (person == '1s' || person == '2s' || person == '3s' || person == '3p');
    rest = elide ? "${me.substring(0, 1)}'$rest" : '$me $rest';
  }
  if (person == '1s' && _vowelStart.hasMatch(rest)) return "j'$rest";
  return '${frenchPronouns[person]} $rest';
}

const _endings = {
  'present-er': ['e', 'es', 'e', 'ons', 'ez', 'ent'],
  'present-ir': ['is', 'is', 'it', 'issons', 'issez', 'issent'],
  'present-re': ['s', 's', '', 'ons', 'ez', 'ent'],
  'imperfect': ['ais', 'ais', 'ait', 'ions', 'iez', 'aient'],
  'future': ['ai', 'as', 'a', 'ons', 'ez', 'ont'],
  'conditional': ['ais', 'ais', 'ait', 'ions', 'iez', 'aient'],
};

/// The regular form of [tense] for [person] on [lemma] (-er / -ir / -re), or
/// null where no pattern is checked.
String? _regularForm(String lemma, String? group, String tense, String person) {
  if (group == null) return null;
  final i = frenchPersons.indexOf(person);
  final stem = lemma.substring(0, lemma.length - 2);
  switch (tense) {
    case 'present':
      return stem + _endings['present$group']![i];
    case 'imperfect':
      // imperfect stem is the present nous form minus -ons: -ir takes -iss-
      return (group == '-ir' ? '${stem}iss' : stem) + _endings['imperfect']![i];
    case 'future':
    case 'conditional':
      final base = group == '-re' ? stem : lemma;
      return base + _endings[tense]![i];
  }
  return null;
}

/// Everything the detail page needs about a French verb, or null when the
/// pack holds no conjugation for it.
FrenchVerb? frenchVerbFrom(String lemma, List<LexForm> forms) {
  final f = _byField(forms);
  final conjugated = forms.any((x) => RegExp(
          r'^fr_(present|imperfect|future|conditional|subjunctive|imperative|simple_past|pluperfect)_[123][sp]$')
      .hasMatch(x.field));
  final pp = f['fr_past_participle'];
  final prp = f['fr_present_participle'];
  if (!conjugated && pp == null && prp == null) return null;
  final pronominal = lemma.startsWith('se ') ||
      lemma.startsWith("s'") ||
      (f['fr_pronominal'] ?? '').isNotEmpty && f['fr_pronominal'] != '0';
  final bare = lemma.replaceFirst(RegExp(r"^(se |s')"), '');
  final end = bare.length > 2 ? bare.substring(bare.length - 2) : '';
  final ending = const {'er', 'ir', 're'}.contains(end) ? '-$end' : null;
  final raw = f['fr_group'];
  var irregular = raw == 'irregular';
  final String? group = ending;

  final auxField = f['fr_auxiliary'];
  final aux = auxField == null
      ? <String>[]
      : [for (final a in _normaliseAux(auxField).split('/')) a];
  // A reflexive verb always takes être.
  final auxiliaries = pronominal && aux.isNotEmpty ? ['être'] : aux;

  final tables = <FrenchTenseTable>[];
  var departures = 0;
  for (final tense in frenchTenses) {
    final cells = <FrenchCell>[];
    if (tense.code == 'passe_compose' || tense.code == 'pluperfect') {
      // Built, not stored: auxiliary + past participle (pluperfect has
      // its own stored forms; it is built only when they are missing).
      if (tense.code == 'pluperfect' &&
          forms.any((x) => x.field.startsWith('fr_pluperfect_'))) {
        // stored forms handled below
      } else if (pp != null && auxiliaries.isNotEmpty) {
        final etre = auxiliaries.length == 1 && auxiliaries.first == 'être';
        for (final p in frenchPersons) {
          final plural = p.endsWith('p');
          final participle = etre ? '$pp${plural ? '(e)s' : '(e)'}' : pp;
          final helper = tense.code == 'pluperfect'
              ? _imperfectOf(auxiliaries.first, p)
              : (auxiliaries.first == 'être' ? _etre[p]! : _avoir[p]!);
          cells.add(FrenchCell(frenchPronouns[p]!,
              _joinSubject(p, '$helper $participle', pronominal && etre)));
        }
      }
    }
    if (cells.isEmpty && tense.code != 'passe_compose') {
      final persons =
          tense.code == 'imperative' ? const ['2s', '1p', '2p'] : frenchPersons;
      for (final p in persons) {
        final value = f['fr_${tense.code}_$p'];
        if (value == null || value.trim().isEmpty) continue;
        final reg = _regularForm(bare, ending, tense.code, p);
        final off = reg != null && reg != value;
        if (off) departures++;
        cells.add(FrenchCell(
            tense.code == 'imperative' ? '' : frenchPronouns[p]!,
            tense.code == 'imperative'
                ? value
                : _joinSubject(p, value, pronominal),
            irregular: off));
      }
    }
    if (cells.isNotEmpty) tables.add(FrenchTenseTable(tense, cells));
  }
  if (!irregular && departures >= 3 && tables.isNotEmpty) irregular = true;
  return FrenchVerb(
    lemma: lemma,
    group: group,
    irregular: irregular,
    auxiliaries: auxiliaries,
    pronominal: pronominal,
    pastParticiple: pp,
    presentParticiple: prp,
    tables: tables,
  );
}

String _imperfectOf(String aux, String p) {
  const avoir = {
    '1s': 'avais',
    '2s': 'avais',
    '3s': 'avait',
    '1p': 'avions',
    '2p': 'aviez',
    '3p': 'avaient'
  };
  const etre = {
    '1s': 'étais',
    '2s': 'étais',
    '3s': 'était',
    '1p': 'étions',
    '2p': 'étiez',
    '3p': 'étaient'
  };
  return aux == 'être' ? etre[p]! : avoir[p]!;
}

/// h aspiré: true / false, or null when the pack does not say.
bool? frenchHAspire(List<LexForm> forms) {
  final v = _byField(forms)['fr_h_aspire'];
  if (v == null) return null;
  return !const {'0', 'false', 'no', 'muet', ''}.contains(v.toLowerCase());
}

/// The noun with its article for the title: le chat, la maison, l'arbre.
/// A word starting with h and no h-aspiré information gets null (the
/// caller falls back to the indefinite article); [plural] true → les.
String? frenchDefiniteArticle(String noun, String gender, {bool? hAspire}) {
  if (gender == 'pl') return 'les $noun';
  final startsH = noun.toLowerCase().startsWith('h');
  final elides = _vowelStart.hasMatch(noun) && !(startsH && hAspire == true);
  if (startsH && hAspire == null) return null;
  if (elides) return "l'$noun";
  return switch (gender) {
    'f' => 'la $noun',
    'm/f' => 'le／la $noun',
    _ => 'le $noun',
  };
}

/// Adjective forms in a 2×2 grid (+ the liaison form bel / nouvel).
class FrenchAdjective {
  final String masculine;
  final String? feminine;
  final String? masculinePlural;
  final String? femininePlural;
  final String? beforeVowel;
  const FrenchAdjective(this.masculine, this.feminine, this.masculinePlural,
      this.femininePlural, this.beforeVowel);
}

FrenchAdjective? frenchAdjectiveFrom(String lemma, List<LexForm> forms) {
  final f = _byField(forms);
  final fem = f['fr_feminine'];
  final pl = f['fr_plural'];
  final fpl = f['fr_feminine_plural'];
  final bel = f['fr_masculine_before_vowel'];
  if ([fem, pl, fpl].where((x) => x != null).length < 2) return null;
  return FrenchAdjective(lemma, fem, pl, fpl, bel);
}
