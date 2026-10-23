import 'dart:convert';
import 'dart:typed_data';

import '../models/photo.dart';
import '../models/word_entry.dart';
import 'deck_library.dart';
import 'learning_content.dart' show posLabel;
import 'lexicon_pack.dart';
import 'word_database_repository.dart';

/// 匯出到 Anki (問題回報 #325): the learner's words as a file Anki can
/// import, for heavy learners who also review in Anki.
///
/// An .apkg is an SQLite database inside a zip, and the app has no SQLite
/// writer (on the web least of all), so the export is the fallback the
/// owner allowed: one zip holding
/// - `english_card_anki.txt`: Anki's text import format (tab separated,
///   `#html:true`, a GUID column so importing again updates the notes
///   instead of duplicating them, and a tags column);
/// - `media/`: the word's photo and recording, named as the notes refer
///   to them (`<img src>`, `[sound:]`);
/// - `匯入說明.txt`: how to import it, and the column order.
///
/// Every note carries the license of its sentences, recording and photo
/// in a 授權 field (and in small print on the back), as CC BY / BY-SA
/// require when the content leaves the app.
class AnkiExport {
  static const notesFile = 'english_card_anki.txt';
  static const guideFile = '匯入說明.txt';
  static const mediaDir = 'media';

  /// Column order of [notesFile]; 1-based in the file's header.
  static const columns = [
    'GUID',
    'Front',
    'Back',
    '英文',
    '詞性',
    '中文',
    '例句',
    '例句翻譯',
    '照片',
    '發音',
    '音標',
    'CEFR',
    '授權',
    '標籤',
  ];

  /// At most this many sentences per note, nearest the learner's level.
  static const maxExamples = 2;

  /// Builds the zip in memory and returns it with what it holds.
  /// [photoBytes] loads a photo's pixels (null when its file is gone);
  /// [assetBytes] loads a bundled file such as the pack's recordings
  /// (`assets/lexicon/media/...`); [lexeme] finds the pack entry of a
  /// word for the recording's and sentences' licenses.
  static Future<AnkiExportResult> build({
    required WordDatabaseRepository repository,
    required AnkiExportScope scope,
    required Future<Uint8List?> Function(Photo photo) photoBytes,
    required Future<Uint8List?> Function(String assetPath) assetBytes,
    LexEntry? Function(int lexemeId)? lexeme,
    String? userLevel,
    DateTime? now,
  }) async {
    final zip = ZipWriter(now: now);
    final media = <String>{};
    final lines = <String>[];
    var photos = 0, audio = 0;
    final level = userLevel ?? repository.profile.cefr;
    for (final e in scope.entries(repository)) {
      final lex = e.lexemeId == null ? null : lexeme?.call(e.lexemeId!);
      final credits = <String>[];

      // Sentences nearest the learner's level, with their licenses.
      final examples =
          e.examplesForLevel(level, minimum: 1, limit: maxExamples);
      final sentenceLicenses = <String>{};
      for (final x in examples) {
        final license = _exampleLicense(x, lex);
        if (license != null) sentenceLicenses.add(license);
      }
      if (sentenceLicenses.isNotEmpty) {
        credits.add('例句：${sentenceLicenses.join('；')}');
      }

      // The word's photo: in this album / deck first, then any.
      var img = '';
      final photo = scope.photoFor(repository, e.id);
      if (photo != null) {
        final name = 'english_card_${_safe(photo.id)}';
        Uint8List? bytes;
        final known = media.where((m) => m.startsWith('$name.')).firstOrNull;
        if (known == null) {
          bytes = await photoBytes(photo);
        }
        final file = known ?? (bytes == null ? null : '$name.${_imageExt(bytes)}');
        if (file != null) {
          if (bytes != null && media.add(file)) {
            zip.add('$mediaDir/$file', bytes);
            photos++;
          }
          img = "<img src='${_attr(file)}'>";
          credits.add('照片：${scope.photoCredit(photo)}');
        }
      }

      // The word recording from the pack (TTS-only words have none).
      var sound = '';
      final url = e.audioUrl;
      if (url != null && url.startsWith('assets/')) {
        final file = 'english_card_${_safe(url.split('/').last)}';
        var ok = media.contains(file);
        if (!ok) {
          final bytes = await assetBytes(url);
          if (bytes != null) {
            zip.add('$mediaDir/$file', bytes);
            media.add(file);
            audio++;
            ok = true;
          }
        }
        if (ok) {
          sound = '[sound:$file]';
          credits.add('發音音檔：${lex?.audioCredit ?? '見各音檔授權'}'
              '（Wikimedia Commons／Wiktionary）');
        }
      }

      final pos = posLabel(e.pos);
      final exampleHtml = [for (final x in examples) _html(x.text)].join('<br>');
      final translationHtml = [
        for (final x in examples)
          _html(x.translation ?? '') +
              (x.aiTranslated && (x.translation ?? '').isNotEmpty
                  ? '（AI 翻譯）'
                  : ''),
      ].join('<br>');
      final creditHtml = credits.map(_html).join('<br>');
      final back = [
        '<div>${_html([pos, e.level].whereType<String>().where((s) => s.isNotEmpty).join(' · '))}</div>',
        '<div><b>${_html(e.meaning)}</b></div>',
        if (img.isNotEmpty) '<div>$img</div>',
        if ((e.ipa ?? '').isNotEmpty || sound.isNotEmpty)
          '<div>${_html(e.ipa ?? '')} $sound</div>',
        for (var i = 0; i < examples.length; i++)
          '<div>${_html(examples[i].text)}<br>'
              "<span style='color:#666'>${_html(examples[i].translation ?? '')}</span></div>",
        if (creditHtml.isNotEmpty)
          "<div style='font-size:smaller;color:#888'>$creditHtml</div>",
      ].join();
      final row = [
        'english-card-${repository.language}-${e.id}',
        _html(e.word),
        back,
        _html(e.word),
        _html(pos),
        _html(e.meaning),
        exampleHtml,
        translationHtml,
        img,
        sound,
        _html(e.ipa ?? ''),
        e.level ?? '',
        creditHtml,
        scope.tagsFor(repository, e).join(' '),
      ];
      lines.add(row.map(_cell).join('\t'));
    }

    final header = [
      '#separator:tab',
      '#html:true',
      '#deck:${_cell('English Card::${scope.title}')}',
      '#guid column:1',
      '#tags column:${columns.length}',
    ];
    zip.add(notesFile, utf8.encode('${[...header, ...lines].join('\n')}\n'));
    zip.add(guideFile, utf8.encode(guide(scope.title, lines.length)));
    return AnkiExportResult(
        bytes: zip.finish(), notes: lines.length, photos: photos, audio: audio);
  }

  /// 匯入說明 in the zip (desktop Anki; AnkiDroid / AnkiMobile alike).
  static String guide(String title, int notes) => '''
English Card → Anki 匯入說明
範圍：$title（$notes 張卡）

1. 解壓縮這個 zip。
2. 把 media 資料夾裡的「所有檔案」（不是資料夾本身）複製到 Anki 的媒體資料夾 collection.media：
   - Windows：%APPDATA%\\Anki2\\<使用者名稱>\\collection.media
   - macOS：~/Library/Application Support/Anki2/<使用者名稱>/collection.media
   - AnkiDroid：AnkiDroid/collection.media
   （桌面版 Anki：工具 → 檢查媒體 → 檢視檔案，可打開這個資料夾。）
3. 在 Anki 選「檔案 → 匯入」，選 $notesFile。
   - 筆記類型選「基本」（Basic）：第 2 欄對到「正面」（Front），第 3 欄對到「背面」（Back），其餘欄位選「（不匯入）」。
   - 想要分開的欄位：先新增一個筆記類型，欄位依序為「英文、詞性、中文、例句、例句翻譯、照片、發音、音標、CEFR、授權」，匯入時把第 4–13 欄對上去。
   - 第 1 欄是 GUID、第 ${columns.length} 欄是標籤，Anki 會自動辨認；同一個檔再匯入一次會更新原本的卡，不會重複。
4. 牌組名稱是「English Card::$title」。

檔案欄位順序：${[for (var i = 0; i < columns.length; i++) '${i + 1} ${columns[i]}'].join('、')}

授權：例句、發音音檔與圖片的作者與授權寫在每張卡的「授權」欄位（背面最下方也有）。
例句來自 Tatoeba（CC BY 2.0 FR）、Wiktionary（CC BY-SA 4.0／GFDL）、Open English WordNet（CC BY 4.0），
音檔來自 Wikimedia Commons／Wiktionary（各檔授權不同）。分享或再發布這些卡片時，請保留授權欄位。
標示「AI 例句」「AI 翻譯」的內容由 AI 產生。
''';

  /// The sentence's license: the pack's, else what its source is
  /// published under (data_sources_screen.dart).
  static String? _exampleLicense(WordExample x, LexEntry? lex) {
    if (x.aiGenerated) return 'AI 例句';
    final fromPack = lex?.examples
        .where((p) => p.text == x.text)
        .map((p) => p.license)
        .whereType<String>()
        .firstOrNull;
    if (fromPack != null && fromPack.trim().isNotEmpty) {
      return '${sourceName(x.source)}，${fromPack.trim()}';
    }
    return switch (x.source) {
      'tatoeba' => 'Tatoeba，CC BY 2.0 FR',
      'kaikki' || 'wiktionary' => 'Wiktionary，CC BY-SA 4.0／GFDL',
      'oewn' => 'Open English WordNet，CC BY 4.0',
      _ => null,
    };
  }

  static String sourceName(String? source) => switch (source) {
        'tatoeba' => 'Tatoeba',
        'kaikki' || 'wiktionary' => 'Wiktionary',
        'oewn' => 'Open English WordNet',
        'ai_translate' => 'AI',
        final s? => s,
        null => '來源不明',
      };

  static String _imageExt(Uint8List b) {
    if (b.length > 3 && b[0] == 0x89 && b[1] == 0x50) return 'png';
    if (b.length > 3 && b[0] == 0x47 && b[1] == 0x49) return 'gif';
    if (b.length > 11 && b[8] == 0x57 && b[9] == 0x45 && b[10] == 0x42) {
      return 'webp';
    }
    return 'jpg';
  }

  static String _safe(String s) => s.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');

  static String _html(String s) => const HtmlEscape(HtmlEscapeMode.element)
      .convert(s)
      .replaceAll('"', '&quot;')
      .replaceAll(RegExp(r'\r\n|\r|\n'), '<br>');

  static String _attr(String s) => _html(s);

  /// One cell: no tab, newline or double quote is left (Anki would read a
  /// quote as CSV quoting), so HTML attributes use single quotes.
  static String _cell(String s) => s
      .replaceAll(RegExp(r'[\t\r\n]'), ' ')
      .replaceAll('"', '&quot;');
}

/// What to export: 全部單字, one album, or one installed 卡片集.
class AnkiExportScope {
  final String title;
  final String? albumId;
  final InstalledDeck? deck;

  const AnkiExportScope.all() : title = '全部單字', albumId = null, deck = null;
  AnkiExportScope.album(Album album)
      : title = '相簿 ${album.name}',
        albumId = album.id,
        deck = null;
  AnkiExportScope.deck(InstalledDeck this.deck)
      : title = '卡片集 ${deck.info.title}',
        albumId = null;

  /// Photos that belong to this scope (none for 全部單字: every photo).
  Set<String>? _photoIds(WordDatabaseRepository repo) {
    if (albumId != null) {
      return {for (final p in repo.photosInAlbum(albumId!)) p.id};
    }
    if (deck != null) return deck!.photoIds.toSet();
    return null;
  }

  /// The words of this scope, in the database's order.
  List<WordEntry> entries(WordDatabaseRepository repo) {
    final photoIds = _photoIds(repo);
    if (photoIds == null) return repo.entries;
    final ids = <String>{
      for (final id in photoIds)
        for (final o in repo.occurrencesInPhoto(id)) o.wordEntryId,
      ...?deck?.entryIds(repo),
    };
    return [
      for (final e in repo.entries)
        if (ids.contains(e.id)) e
    ];
  }

  Photo? photoFor(WordDatabaseRepository repo, String wordEntryId) {
    final all = repo.photosOfWord(wordEntryId);
    final own = _photoIds(repo);
    return (own == null ? null : all.where((p) => own.contains(p.id)).firstOrNull) ??
        all.firstOrNull;
  }

  String photoCredit(Photo p) {
    if (p.credit != null) return p.credit!;
    if (p.id.startsWith('photo-deck-')) {
      return '卡片集圖片（作者與授權見 App「資料來源與授權」：Wikimedia Commons 等，各圖授權不同）';
    }
    if (p.assetPath != null) return 'English Card 範例照片';
    return '你自己的照片';
  }

  /// Anki tags (no spaces): EnglishCard, the CEFR level, part of speech,
  /// the word's albums and decks, 已學會 for archived words.
  List<String> tagsFor(WordDatabaseRepository repo, WordEntry e) {
    String tag(String s) => s.trim().replaceAll(RegExp(r'\s+'), '_');
    final albums = {
      for (final p in repo.photosOfWord(e.id))
        if (p.albumId != null) repo.album(p.albumId!)?.name,
    }.whereType<String>();
    return {
      'EnglishCard',
      if ((e.level ?? '').isNotEmpty) 'CEFR::${e.level}',
      if (e.pos.isNotEmpty) 'EnglishCard::${tag(posLabel(e.pos))}',
      for (final a in albums) 'EnglishCard::相簿::${tag(a)}',
      if (deck != null) 'EnglishCard::卡片集::${tag(deck!.info.title)}',
      for (final t in e.tags)
        if (t.trim().isNotEmpty) tag(t),
      if (repo.isArchived(e.id)) 'EnglishCard::已學會',
    }.where((t) => t.isNotEmpty).toList();
  }
}

class AnkiExportResult {
  final Uint8List bytes;
  final int notes;
  final int photos;
  final int audio;
  const AnkiExportResult(
      {required this.bytes,
      required this.notes,
      required this.photos,
      required this.audio});
}

/// A zip of uncompressed ("stored") entries — photos and mp3s are already
/// compressed — in plain Dart, so it works on the web too. File names are
/// UTF-8 (general purpose flag bit 11).
class ZipWriter {
  final _out = BytesBuilder(copy: false);
  final _central = BytesBuilder(copy: false);
  var _count = 0;
  final int _dosTime;
  final int _dosDate;

  ZipWriter({DateTime? now})
      : _dosTime = _time(now ?? DateTime.now()),
        _dosDate = _date(now ?? DateTime.now());

  static int _time(DateTime d) =>
      (d.hour << 11) | (d.minute << 5) | (d.second ~/ 2);
  static int _date(DateTime d) =>
      ((d.year - 1980).clamp(0, 127) << 9) | (d.month << 5) | d.day;

  void add(String name, List<int> data) {
    final nameBytes = utf8.encode(name);
    final crc = crc32(data);
    final offset = _out.length;
    void common(BytesBuilder b) {
      _u16(b, 20); // version needed
      _u16(b, 0x0800); // UTF-8 names
      _u16(b, 0); // stored
      _u16(b, _dosTime);
      _u16(b, _dosDate);
      _u32(b, crc);
      _u32(b, data.length);
      _u32(b, data.length);
      _u16(b, nameBytes.length);
      _u16(b, 0); // extra
    }

    _u32(_out, 0x04034b50);
    common(_out);
    _out.add(nameBytes);
    _out.add(data);

    _u32(_central, 0x02014b50);
    _u16(_central, 20); // version made by
    common(_central);
    _u16(_central, 0); // comment
    _u16(_central, 0); // disk
    _u16(_central, 0); // internal attributes
    _u32(_central, 0); // external attributes
    _u32(_central, offset);
    _central.add(nameBytes);
    _count++;
  }

  Uint8List finish() {
    final start = _out.length;
    final dir = _central.takeBytes();
    _out.add(dir);
    _u32(_out, 0x06054b50);
    _u16(_out, 0);
    _u16(_out, 0);
    _u16(_out, _count);
    _u16(_out, _count);
    _u32(_out, dir.length);
    _u32(_out, start);
    _u16(_out, 0);
    return _out.takeBytes();
  }

  static void _u16(BytesBuilder b, int v) => b.add([v & 0xff, (v >> 8) & 0xff]);
  static void _u32(BytesBuilder b, int v) => b.add(
      [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >> 24) & 0xff]);

  static final _table = List<int>.generate(256, (n) {
    var c = n;
    for (var k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
    }
    return c;
  });

  static int crc32(List<int> data) {
    var c = 0xFFFFFFFF;
    for (final b in data) {
      c = _table[(c ^ b) & 0xff] ^ (c >> 8);
    }
    return (c ^ 0xFFFFFFFF) & 0xFFFFFFFF;
  }
}
