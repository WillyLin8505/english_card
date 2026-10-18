import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/tagging_progress.dart';
import 'helpers.dart';

void main() {
  for (final status in [503, 502, 422]) {
    testWidgets('batch progress survives response $status and retry',
        (tester) async {
      final repo = WordDatabaseRepository(clock: () => testNow);
      final store = PhotoStore.inMemory();
      final replies = List.generate(4, (_) => Completer<http.Response>());
      var calls = 0;
      final queue = TaggingQueue(
        repository: () => repo,
        settings:
            AppSettings.inMemory(taggingUrl: 'http://test/tag', apiKey: 'test'),
        lexicon: testLexicon,
        intake: PhotoIntake(
            repository: () => repo,
            photoStore: store,
            createTagger: (uri, key) => TaggingService(
                endpoint: uri,
                apiKey: key,
                client: MockClient((_) => replies[calls++].future))),
      );
      for (var i = 0; i < 3; i++) {
        final saved = await store.save('p$i', Uint8List.fromList([1, 2, 3]));
        repo.addPhoto(Photo(
            id: 'p$i',
            title: 'photo',
            takenAt: testNow,
            createdAt: testNow.add(Duration(minutes: i)),
            storedKey: saved.storedKey,
            taggingStatus: TaggingStatus.pending));
      }
      await tester.pumpWidget(MaterialApp(
          builder: (context, child) =>
              TaggingProgress(queue: queue, child: child!),
          home: const Scaffold()));
      var processing = queue.process();
      // The app owns this timer, independently of the page's lifetime.
      if (status == 503) queue.start();
      await tester.pump();
      replies[0].complete(jsonResponse({'candidates': []}));
      await tester.pump();
      expect(find.textContaining('第 2/3 張'), findsOneWidget);
      replies[1].complete(
          http.Response('{"error":"temporarily unavailable"}', status));
      await tester.pump();
      await tester.pump();
      if (status != 422) {
        await processing;
        expect(queue.completed, 1);
        expect(queue.failed, 0);
        expect(repo.photo('p1')!.taggingStatus, TaggingStatus.pending);
        expect(find.textContaining('已處理 1/3 張'), findsOneWidget);
        expect(find.textContaining('會自動重試'), findsOneWidget);
        if (status == 503) {
          await tester.pump(const Duration(minutes: 1));
        } else {
          processing = queue.process();
        }
        await tester.pump();
        expect(find.textContaining('第 2/3 張'), findsOneWidget);
        replies[2].complete(jsonResponse({'candidates': []}));
        await tester.pump();
        await tester.pump();
        expect(find.textContaining('第 3/3 張'), findsOneWidget);
        replies[3].complete(jsonResponse({'candidates': []}));
      } else {
        expect(queue.failed, 1);
        expect(repo.photo('p1')!.taggingStatus, TaggingStatus.failed);
        expect(find.textContaining('第 3/3 張'), findsOneWidget);
        expect(find.textContaining('1 張辨識失敗'), findsOneWidget);
        replies[2].complete(jsonResponse({'candidates': []}));
      }
      await tester.pump();
      await processing;
      await tester.pump();
      expect(queue.completed, 3);
      expect(queue.hasWork, isFalse);
      expect(queue.estimatedRemaining, Duration.zero);
      expect(find.textContaining('AI 打標籤'), findsNothing);
      // An idle poll must not resurrect the finished batch.
      await queue.process();
      expect(queue.total, 0);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      queue.dispose();
    });
  }

  testWidgets('progress survives navigation and includes newly queued photos',
      (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final store = PhotoStore.inMemory();
    final replies = [Completer<http.Response>(), Completer<http.Response>()];
    var calls = 0;
    final queue = TaggingQueue(
      repository: () => repo,
      settings:
          AppSettings.inMemory(taggingUrl: 'http://test/tag', apiKey: 'test'),
      lexicon: testLexicon,
      intake: PhotoIntake(
          repository: () => repo,
          photoStore: store,
          createTagger: (uri, key) => TaggingService(
              endpoint: uri,
              apiKey: key,
              client: MockClient((_) => replies[calls++].future))),
    );
    addTearDown(queue.dispose);
    Future<void> addPhoto(int i) async {
      final saved = await store.save('p$i', Uint8List.fromList([1, 2, 3]));
      repo.addPhoto(Photo(
          id: 'p$i',
          title: 'photo',
          takenAt: testNow,
          createdAt: testNow.add(Duration(minutes: i)),
          storedKey: saved.storedKey,
          taggingStatus: TaggingStatus.pending));
    }

    await addPhoto(0);
    final nav = GlobalKey<NavigatorState>();
    await tester.pumpWidget(MaterialApp(
        navigatorKey: nav,
        builder: (context, child) =>
            TaggingProgress(queue: queue, child: child!),
        home: const Scaffold(body: Text('photos'))));
    final processing = queue.process();
    await tester.pump();
    expect(find.textContaining('第 1/1 張'), findsOneWidget);
    expect(queue.estimatedRemaining.inSeconds, inInclusiveRange(59, 60));
    await addPhoto(1);
    await tester.pump(const Duration(seconds: 1));
    expect(find.textContaining('第 1/2 張'), findsOneWidget);
    nav.currentState!.push(MaterialPageRoute<void>(
        builder: (_) => const Scaffold(body: Text('another page'))));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('another page'), findsOneWidget);
    expect(find.textContaining('第 1/2 張'), findsOneWidget);
    expect(calls, 1);
    replies[0].complete(jsonResponse({'candidates': []}));
    await tester.pump();
    expect(queue.completed, 1);
    expect(find.textContaining('第 2/2 張'), findsOneWidget);
    expect(queue.estimatedRemaining.inSeconds, greaterThan(0));
    replies[1].complete(jsonResponse({'candidates': []}));
    await tester.pump();
    await processing;
    expect(queue.completed, 2);
    expect(queue.current, isNull);
    expect(find.textContaining('AI 打標籤'), findsNothing);
    expect(repo.allPhotos.every((p) => p.taggingStatus == TaggingStatus.done),
        isTrue);
    expect(tester.takeException(), isNull);
  });
}
