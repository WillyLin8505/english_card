import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/app/app_shell.dart';
import 'package:photo_english_app/data/sample_word_database.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/cefr_lexicon.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_enricher.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

final testNow = DateTime(2026, 9, 23, 10);

CefrLexicon? _lexicon;

/// The real bundled word list (assets/cefr_en.json), read from disk.
CefrLexicon testLexicon() => _lexicon ??= CefrLexicon.fromJson(
    jsonDecode(File('assets/cefr_en.json').readAsStringSync())
        as Map<String, dynamic>);

/// The sample database with levels corrected by the real word list.
WordDatabaseRepository testRepository({DateTime? now}) =>
    sampleWordDatabase(now: now ?? testNow, lexicon: testLexicon());

http.Response jsonResponse(Object body, [int status = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

class TestApp {
  final WordDatabaseRepository repository;
  final AppSettings settings;
  final PhotoStore photoStore;
  final AppNavigatorProxy navigator;
  final TaggingQueue queue;
  final WordEnricher enricher;
  final Speaker speaker;

  TestApp(this.repository, this.settings, this.photoStore, this.navigator,
      this.queue, this.enricher, this.speaker);
}

/// Pumps the whole app (shell + tabs) with the sample data, at the Figma
/// frames' 402×874, with the status-bar inset a phone would have. The
/// background workers are built but not started.
Future<TestApp> pumpApp(
  WidgetTester tester, {
  AppTab initialTab = AppTab.camera,
  AppSettings? settings,
  PhotoStore? photoStore,
  Widget? home,
  WordDatabaseRepository? repository,
  TaggingService Function(Uri, String)? createTagger,
  Size size = const Size(402, 874),
  bool databaseLibrary = false,
  Speaker? speaker,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  tester.view.padding = const FakeViewPadding(top: 44);
  addTearDown(tester.view.reset);

  final repo = repository ?? testRepository();
  final s = settings ?? AppSettings.inMemory();
  final photos = photoStore ?? PhotoStore.inMemory();
  final nav = AppNavigatorProxy();
  final intake = PhotoIntake(
      repository: () => repo, photoStore: photos, createTagger: createTagger);
  final queue = TaggingQueue(
      repository: () => repo,
      settings: s,
      intake: intake,
      lexicon: testLexicon);
  final enricher = WordEnricher(
      repository: () => repo,
      settings: s,
      intake: intake,
      lexicon: testLexicon,
      queue: queue);
  final spk = speaker ?? SilentSpeaker();
  await tester.pumpWidget(AppScope(
    repository: repo,
    settings: s,
    photoStore: photos,
    intake: intake,
    queue: queue,
    enricher: enricher,
    speaker: spk,
    lexicon: testLexicon(),
    navigator: nav,
    switchLanguage: (_) async {},
    clock: () => testNow,
    child: MaterialApp(
      theme: MobileTheme.light(),
      home: home ??
          AppShell(
              initialTab: initialTab,
              databaseLibrary: databaseLibrary,
              onNavigatorReady: (n) => nav.target = n),
    ),
  ));
  await tester.pump();
  return TestApp(repo, s, photos, nav, queue, enricher, spk);
}

/// Lets real async work (HTTP mocks, microtasks) finish between frames.
Future<void> settle(WidgetTester tester, {int rounds = 3}) async {
  for (var i = 0; i < rounds; i++) {
    await tester
        .runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pumpAndSettle();
  }
}

/// Starts a 複習 run from the 複習 tab: since #440/#446 the tab opens on a
/// grid of books (tap 綜合); an album-scoped screen still shows 開始複習.
/// [label] maps a Chinese label to the UI language under test. Returns false
/// when neither is on screen (nothing to review).
Future<bool> startReview(WidgetTester tester,
    {String Function(String) label = _same}) async {
  for (final text in ['綜合', '開始複習']) {
    final f = find.text(label(text));
    if (f.evaluate().isNotEmpty) {
      await tester.tap(f.first);
      await tester.pumpAndSettle();
      return true;
    }
  }
  return false;
}

String _same(String s) => s;
