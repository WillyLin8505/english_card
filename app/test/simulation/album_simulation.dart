// Album UI simulation (not part of the regular suite).
//
// Ten albums of real tagger replies: each album is opened, searched for one
// of its words, a photo opened and left, and the album's word count checked
// against the words actually studied in it (spec: 相片冊縮圖不顯示已學會標籤).
//
//   flutter test test/simulation/album_simulation.dart  (SIM_PACK)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('learner browses albums', (tester) async {
    final rnd = Random(5);
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(Platform.environment['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final replies = [
      for (final f in Directory('../tagger/cache').listSync().whereType<File>())
        if (!f.uri.pathSegments.last.startsWith('score-')) f
    ]..sort((a, b) => a.path.compareTo(b.path));
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    final f = Findings();
    final albums = [for (var a = 0; a < 10; a++) repo.addAlbum(name: '旅行 $a', category: a.isEven ? '生活' : '美食')];
    var n = 0;
    for (final album in albums) {
      for (var k = 0; k < 20; k++) {
        final raw = jsonDecode(replies[rnd.nextInt(replies.length)].readAsStringSync());
        final id = 'a${n++}';
        repo.addPhoto(Photo(
            id: id, albumId: album.id, title: id, takenAt: testNow, createdAt: testNow,
            placeholderColors: const [0xFF8899AA, 0xFF334455],
            taggingStatus: TaggingStatus.done,
            candidates: pack.linkAll(parseCandidates(raw, lexicon: testLexicon()))));
        final s = PhotoWordSession(repo: repo, photoId: id);
        if (s.words.isNotEmpty && rnd.nextDouble() < 0.3) s.swipe(s.words.first);
        s.save();
        s.dispose();
      }
    }
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) => f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);
    await pumpApp(tester, initialTab: AppTab.album, repository: repo, size: const Size(390, 844));
    await tester.pumpAndSettle();
    for (final album in albums) {
      current = album.name;
      final studied = {
        for (final p in repo.photosInAlbum(album.id))
          for (final l in repo.activeLabels(p.id)) l.entry.id,
      };
      if (repo.albumWordCount(album.id) != studied.length) {
        f.add('相簿單字數和實際不同', '${album.name}：${repo.albumWordCount(album.id)} vs ${studied.length}');
      }
      final card = find.bySemanticsLabel(RegExp('^${album.name}，'));
      if (card.evaluate().isEmpty) {
        // Albums are grouped by category; switch to the other one.
        final other = find.text(album.category == '生活' ? '生活' : '美食');
        if (other.evaluate().isNotEmpty) {
          await tester.tap(other.first);
          await tester.pumpAndSettle();
        }
      }
      if (card.evaluate().isEmpty) {
        f.add('相簿卡片找不到', album.name);
        continue;
      }
      await tester.ensureVisible(card.first);
      await tester.tap(card.first);
      await tester.pumpAndSettle();
      final words = [for (final p in repo.photosInAlbum(album.id)) for (final l in repo.activeLabels(p.id)) l.entry.word];
      if (words.isNotEmpty) {
        final field = find.byType(TextField);
        if (field.evaluate().isNotEmpty) {
          await tester.enterText(field.first, words.first);
          await tester.pumpAndSettle();
        }
      }
      final back = find.bySemanticsLabel('返回');
      if (back.evaluate().isNotEmpty) {
        await tester.tap(back.first);
        await tester.pumpAndSettle();
      }
    }
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'albums': albums.length, 'photos': repo.photos.length, 'findings': f.toJson()}));
  }, timeout: const Timeout(Duration(minutes: 10)));
}
