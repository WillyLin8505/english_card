import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/anki_export.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 匯出到 Anki (card #328, 問題回報 #325): a zip with Anki's text import
/// file, the photos and recordings it refers to, and how to import it;
/// every note credits its sentences, recording and photo.
void main() {
  /// name → bytes of a stored zip, read through its local headers, checking
  /// each entry's CRC.
  Map<String, Uint8List> unzip(Uint8List z) {
    final out = <String, Uint8List>{};
    final d = ByteData.sublistView(z);
    var i = 0;
    while (d.getUint32(i, Endian.little) == 0x04034b50) {
      expect(d.getUint16(i + 8, Endian.little), 0, reason: 'stored');
      final crc = d.getUint32(i + 14, Endian.little);
      final size = d.getUint32(i + 18, Endian.little);
      final nameLen = d.getUint16(i + 26, Endian.little);
      final extra = d.getUint16(i + 28, Endian.little);
      final name = utf8.decode(z.sublist(i + 30, i + 30 + nameLen));
      final start = i + 30 + nameLen + extra;
      final data = z.sublist(start, start + size);
      expect(ZipWriter.crc32(data), crc, reason: name);
      out[name] = data;
      i = start + size;
    }
    // The central directory lists the same entries.
    final end = z.length - 22;
    expect(d.getUint32(end, Endian.little), 0x06054b50);
    expect(d.getUint16(end + 10, Endian.little), out.length);
    return out;
  }

  final jpeg = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 1, 2, 3]);
  final mp3 = Uint8List.fromList([0x49, 0x44, 0x33, 4, 5]);
  const audioPath = 'assets/lexicon/media/audio/en/abc.mp3';

  LexEntry lexApple() => const LexEntry(
        id: 11,
        lemma: 'apple',
        normalized: 'apple',
        pos: 'noun',
        status: 'full',
        audioCredit: 'CC BY-SA 4.0 · Own work',
        examples: [
          LexExample('I like "red" apples.', '我喜歡紅蘋果。', false, 'tatoeba', 'A1',
              license: 'CC BY 2.0 FR'),
        ],
      );

  (WordDatabaseRepository, Album, Photo) env() {
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [
      WordEntry(
        id: 'w-apple',
        word: 'apple',
        pos: 'noun',
        meaning: '蘋果',
        ipa: '/ˈæp.əl/',
        audioUrl: audioPath,
        level: 'A1',
        lexemeId: 11,
        examples: const [
          WordExample(
              text: 'I like "red" apples.',
              translation: '我喜歡紅蘋果。',
              source: 'tatoeba',
              difficulty: 'A1'),
        ],
        createdAt: testNow,
        updatedAt: testNow,
      ),
      WordEntry(
        id: 'w-run',
        word: 'run',
        pos: 'verb',
        meaning: '跑',
        level: 'A2',
        examples: const [
          WordExample(
              text: 'Run\tfast.',
              translation: '快跑。',
              source: 'ai_translate',
              difficulty: 'A2',
              aiGenerated: true,
              aiTranslated: true),
        ],
        createdAt: testNow,
        updatedAt: testNow,
      ),
    ]);
    final album = repo.addAlbum(name: '我的 廚房');
    final photo = Photo(
        id: 'photo-1',
        albumId: album.id,
        title: '廚房',
        takenAt: testNow,
        createdAt: testNow,
        storedKey: 'k1');
    repo.addPhoto(photo);
    repo.savePhotoWords(photo.id, [
      const ListedWord(
          WordCandidate(
              word: 'apple',
              pos: 'noun',
              meaning: '蘋果',
              level: 'A1',
              levelSource: 'user',
              point: LabelPoint(0.5, 0.5)),
          LabelPoint(0.5, 0.5)),
    ], difficultyOffset: 0);
    return (repo, album, repo.photo('photo-1')!);
  }

  Future<AnkiExportResult> build(WordDatabaseRepository repo,
          AnkiExportScope scope) =>
      AnkiExport.build(
        repository: repo,
        scope: scope,
        photoBytes: (p) async => p.id == 'photo-1' ? jpeg : null,
        assetBytes: (path) async => path == audioPath ? mp3 : null,
        lexeme: (id) => id == 11 ? lexApple() : null,
        userLevel: 'A1',
        now: testNow,
      );

  List<List<String>> rows(Map<String, Uint8List> files) {
    final text = utf8.decode(files[AnkiExport.notesFile]!);
    return [
      for (final line in const LineSplitter().convert(text))
        if (!line.startsWith('#')) line.split('\t')
    ];
  }

  test('crc32 matches the standard check value', () {
    expect(ZipWriter.crc32(utf8.encode('123456789')), 0xCBF43926);
  });

  test('全部單字: notes file, guide and media, with every field', () async {
    final (repo, _, _) = env();
    final r = await build(repo, const AnkiExportScope.all());
    expect((r.notes, r.photos, r.audio), (2, 1, 1));
    final files = unzip(r.bytes);
    expect(files.keys.toSet(), {
      'media/english_card_photo-1.jpg',
      'media/english_card_abc.mp3',
      AnkiExport.notesFile,
      AnkiExport.guideFile,
    });
    expect(files['media/english_card_photo-1.jpg'], jpeg);

    final text = utf8.decode(files[AnkiExport.notesFile]!);
    expect(text, startsWith('#separator:tab\n#html:true\n'));
    expect(text, contains('#deck:English Card::全部單字'));
    expect(text, contains('#guid column:1'));
    expect(text, contains('#tags column:14'));
    // No raw double quote anywhere: Anki would treat it as CSV quoting.
    expect(text.contains('"'), isFalse);

    final all = rows(files);
    expect(all.every((r) => r.length == AnkiExport.columns.length), isTrue);
    final apple = all.firstWhere((r) => r[3] == 'apple');
    expect(apple[0], 'english-card-en-w-apple');
    expect(apple[1], 'apple');
    expect(apple[4], '名詞');
    expect(apple[5], '蘋果');
    expect(apple[6], 'I like &quot;red&quot; apples.');
    expect(apple[7], '我喜歡紅蘋果。');
    expect(apple[8], "<img src='english_card_photo-1.jpg'>");
    expect(apple[9], '[sound:english_card_abc.mp3]');
    expect(apple[10], '/ˈæp.əl/');
    expect(apple[11], 'A1');
    expect(apple[12], contains('例句：Tatoeba，CC BY 2.0 FR'));
    expect(apple[12], contains('發音音檔：CC BY-SA 4.0 · Own work'));
    expect(apple[12], contains('照片：你自己的照片'));
    expect(apple[2], contains("<img src='english_card_photo-1.jpg'>"));
    expect(apple[2], contains('[sound:english_card_abc.mp3]'));
    expect(apple[2], contains('CC BY 2.0 FR'));
    expect(apple[13].split(' '),
        containsAll(['EnglishCard', 'CEFR::A1', 'EnglishCard::相簿::我的_廚房']));

    final run = all.firstWhere((r) => r[3] == 'run');
    expect(run[6], 'Run fast.', reason: 'tab inside a sentence is a space');
    expect(run[7], '快跑。（AI 翻譯）');
    expect(run[12], '例句：AI 例句');
    expect(run[8], isEmpty);
    expect(run[9], isEmpty);

    final guide = utf8.decode(files[AnkiExport.guideFile]!);
    expect(guide, contains('collection.media'));
    expect(guide, contains('授權'));
  });

  test('相簿: only the album\'s words', () async {
    final (repo, album, _) = env();
    final r = await build(repo, AnkiExportScope.album(album));
    final all = rows(unzip(r.bytes));
    expect(all.map((r) => r[3]), ['apple']);
    expect(utf8.decode(unzip(r.bytes)[AnkiExport.notesFile]!),
        contains('#deck:English Card::相簿 我的 廚房'));
  });

  test('卡片集: the deck\'s words and pictures, credited as deck pictures',
      () async {
    final (repo, _, photo) = env();
    final deck = InstalledDeck(
      info: const DeckInfo(slug: 's', kind: 'words', title: '基礎', count: 1),
      installedAt: testNow,
      photoIds: const [],
      wordEntryIds: const ['w-run'],
    );
    final r = await build(repo, AnkiExportScope.deck(deck));
    final all = rows(unzip(r.bytes));
    expect(all.map((r) => r[3]), ['run']);
    expect(all.single[13], contains('EnglishCard::卡片集::基礎'));
    expect(AnkiExportScope.deck(deck).photoCredit(photo), '你自己的照片');
    expect(
        AnkiExportScope.deck(deck).photoCredit(Photo(
            id: 'photo-deck-1',
            title: '',
            takenAt: testNow,
            createdAt: testNow)),
        contains('卡片集圖片'));
  });

  test('a photo whose file is gone is left out, the note still exports',
      () async {
    final (repo, _, _) = env();
    final r = await AnkiExport.build(
      repository: repo,
      scope: const AnkiExportScope.all(),
      photoBytes: (_) async => null,
      assetBytes: (_) async => null,
      now: testNow,
    );
    expect((r.notes, r.photos, r.audio), (2, 0, 0));
    final apple = rows(unzip(r.bytes)).firstWhere((r) => r[3] == 'apple');
    expect(apple[8], isEmpty);
    expect(apple[9], isEmpty);
    // Without the pack, the sentence license comes from its source.
    expect(apple[12], '例句：Tatoeba，CC BY 2.0 FR');
  });
}
