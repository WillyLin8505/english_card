import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:path_provider/path_provider.dart';
import 'package:sqlite3/sqlite3.dart';

import '../models/word_detail.dart';

/// One word found in the compact offline dictionary (card #1075, 問題回報
/// #1598): spelling, part of speech, meaning, IPA — nothing else.
class CompactHit {
  const CompactHit(
      {required this.typed,
      required this.word,
      required this.pos,
      required this.gloss,
      this.ipa,
      this.viaForm = false});

  /// What was looked up, and the headword it resolved to (went → go).
  final String typed;
  final String word;

  /// App part of speech ('noun', 'verb', 'adj.', 'adv.', or '' when unknown).
  final String pos;
  final String gloss;
  final String? ipa;
  final bool viaForm;

  /// The 1–2 first meanings, without the part-of-speech prefixes.
  String get meaning {
    final lines = gloss
        .split('\n')
        .map((l) => _splitPosLine(l).$2)
        .where((l) => l.isNotEmpty)
        .take(2);
    return lines.join('；');
  }

  Definition _definition(String line) {
    final (linePos, text) = _splitPosLine(line);
    return Definition(pos: linePos.isEmpty ? pos : linePos, gloss: text);
  }

  WordDetail toDetail(String source) => WordDetail(
        word: word,
        definitions: [
          for (final l in gloss.split('\n'))
            if (l.trim().isNotEmpty) _definition(l),
        ],
        definitionsSource: source,
        ipa: ipa,
        ipaSource: ipa == null ? null : source,
      );
}

/// The compact offline dictionary, one SQLite file per language pair
/// (`assets/compact/compact_<target>_<native>.sqlite`, built by
/// `lexicon/tools/card1075_build_compact.py`). Copied from the app bundle to
/// the app's support folder on first use, then opened read-only. Used after
/// the full lexicon pack has nothing for a word.
class CompactDictionary {
  CompactDictionary._();
  static final CompactDictionary instance = CompactDictionary._();
  static const supported = true;
  static const sourceLabel = '精簡字典';

  final _dbs = <String, Database?>{};

  static String _key(String target, String native) => '${target}_$native';

  Future<void> open(String target, String native) async {
    if (kIsWeb) return;
    final key = _key(target, native);
    if (_dbs.containsKey(key)) return;
    _dbs[key] = null;
    try {
      final data = await rootBundle.load('assets/compact/compact_$key.sqlite');
      final dir = await getApplicationSupportDirectory();
      final file = File('${dir.path}/compact/compact_$key.sqlite');
      if (!file.existsSync() || file.lengthSync() != data.lengthInBytes) {
        await file.parent.create(recursive: true);
        await file.writeAsBytes(
            data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
            flush: true);
      }
      _dbs[key] = sqlite3.open(file.path, mode: OpenMode.readOnly);
    } catch (e) {
      debugPrint('CompactDictionary($key) unavailable: $e');
    }
  }

  /// Opens an existing file (tests).
  void openFile(String target, String native, String path) =>
      _dbs[_key(target, native)] = sqlite3.open(path, mode: OpenMode.readOnly);

  bool isOpen(String target, String native) =>
      _dbs[_key(target, native)] != null;

  CompactHit? lookup(String word, String target, String native) {
    final db = _dbs[_key(target, native)];
    if (db == null) return null;
    final w = word.trim().toLowerCase().replaceAll('’', "'");
    if (w.isEmpty) return null;
    var row = _row(db, w);
    if (row == null) return null;
    var viaForm = false;
    final lemma = row['lemma'] as String? ?? '';
    // went → go: the form's own line only says 「go的過去式」; show go.
    if (lemma.isNotEmpty) {
      final base = _row(db, lemma);
      if (base != null) {
        row = base;
        viaForm = true;
      }
    }
    final ipa = (row['ipa'] as String?)?.trim();
    return CompactHit(
        typed: w,
        word: row['word'] as String,
        pos: _appPos(row['pos'] as String? ?? ''),
        gloss: row['gloss'] as String? ?? '',
        ipa: ipa == null || ipa.isEmpty ? null : ipa,
        viaForm: viaForm);
  }

  static Row? _row(Database db, String w) {
    final r = db.select(
        'SELECT word, pos, gloss, ipa, lemma FROM w WHERE word = ?', [w]);
    return r.isEmpty ? null : r.first;
  }

  /// The asset stores App values already (card #1098); the ECDICT codes are
  /// still accepted so an older asset shows the same labels.
  static String _appPos(String p) => switch (p) {
        'n' || 'noun' => 'noun',
        'v' || 'vt' || 'vi' || 'verb' => 'verb',
        'a' || 'adj' || 'adj.' => 'adj',
        'ad' || 'adv' || 'adv.' => 'adv',
        'prep' => 'prep',
        'conj' => 'conj',
        'int' || 'intj' => 'intj',
        'pron' => 'pron',
        'num' => 'num',
        _ => '',
      };
}

/// Splits 「名詞：銀行」 (the asset's label, card #1098) into ('noun', '銀行').
/// A line without a label keeps its text; the ECDICT 「n. 銀行」 form is read too.
(String, String) _splitPosLine(String line) {
  final t = line.trim();
  final label = RegExp(r'^(名詞|動詞|形容詞|副詞|介系詞|連接詞|感嘆詞|代名詞|數詞)：\s*')
      .firstMatch(t);
  if (label != null) {
    return (_labelPos[label.group(1)!]!, t.substring(label.end));
  }
  final code = RegExp(r'^([a-z]{1,6})\.\s*(.*)$').firstMatch(t);
  if (code != null) {
    return (CompactDictionary._appPos(code.group(1)!), code.group(2)!);
  }
  return ('', t);
}

const _labelPos = {
  '名詞': 'noun',
  '動詞': 'verb',
  '形容詞': 'adj',
  '副詞': 'adv',
  '介系詞': 'prep',
  '連接詞': 'conj',
  '感嘆詞': 'intj',
  '代名詞': 'pron',
  '數詞': 'num',
};
