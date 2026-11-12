import '../models/word_detail.dart';

/// Web build of [CompactDictionary] (card #1075): no dart:ffi, no SQLite, so
/// there is no compact offline dictionary in the browser.
class CompactHit {
  const CompactHit(
      {required this.typed,
      required this.word,
      required this.pos,
      required this.gloss,
      this.ipa,
      this.viaForm = false});
  final String typed;
  final String word;
  final String pos;
  final String gloss;
  final String? ipa;
  final bool viaForm;
  String get meaning => gloss;
  WordDetail toDetail(String source) => WordDetail(word: word);
}

class CompactDictionary {
  CompactDictionary._();
  static final CompactDictionary instance = CompactDictionary._();
  static const supported = false;
  static const sourceLabel = '精簡字典';
  Future<void> open(String target, String native) async {}
  void openFile(String target, String native, String path) {}
  bool isOpen(String target, String native) => false;
  CompactHit? lookup(String word, String target, String native) => null;
}
