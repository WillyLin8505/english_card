/// Web build of [LexiconSqlite] (card #428): `package:sqlite3` needs
/// dart:ffi, so the browser keeps the JSON pack and every method here is
/// unreachable — [LexiconPack] and [DictionarySync] check [supported] first.
class LexiconSqlite {
  LexiconSqlite._();

  static const formatVersion = 1;
  static const supported = false;
  static const bodyKeys = <String>{};

  String get path => throw UnsupportedError('No SQLite on the web');
  bool get closed => true;

  static LexiconSqlite open(String path, {bool readOnly = false}) =>
      throw UnsupportedError('No SQLite on the web');

  static ({String? target, String? native, String? version})? inspect(
          String path) =>
      null;

  Map<String, dynamic> meta({Set<String>? keys}) => const {};
  Iterable<Map<String, dynamic>> heads() => const [];
  int get rowCount => 0;
  List<dynamic>? senses(int id) => null;
  Map<String, dynamic>? body(int id) => null;
  void applyDelta(Map<String, dynamic> patch) =>
      throw UnsupportedError('No SQLite on the web');
  void close() {}

  static void build(Map<String, dynamic> pack, String path) =>
      throw UnsupportedError('No SQLite on the web');
}
