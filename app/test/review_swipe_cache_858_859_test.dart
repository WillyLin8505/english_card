// 問題回報 #858 (複習：滑動圖片存在卡頓) and #859 (載入圖片需要時間？可以用
// 快取的方式減低圖片讀取嗎).
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/pack_media.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_cache.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

// A 1×1 PNG.
final _png = Uint8List.fromList([
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

// Each test its own URLs: the image cache keeps a previous test's images.
var _run = 0;

Photo _photo(String id) => Photo(
      id: id,
      title: '',
      takenAt: testNow,
      createdAt: testNow,
      networkUrl: 'https://photos.test/858/$_run/$id.jpg',
      width: 4000,
      height: 3000,
    );

void main() {
  final defaultFetch = CachedNetworkPhoto.fetch;
  final defaultDirectory = CachedNetworkPhoto.cacheDirectory;
  final defaultMaxFiles = CachedNetworkPhoto.maxFiles;
  final fetched = <String>[];

  setUp(() {
    fetched.clear();
    CachedNetworkPhoto.fetch = (uri) async {
      fetched.add('$uri');
      return _png;
    };
  });
  tearDown(() {
    CachedNetworkPhoto.fetch = defaultFetch;
    CachedNetworkPhoto.cacheDirectory = defaultDirectory;
    CachedNetworkPhoto.maxFiles = defaultMaxFiles;
    PaintingBinding.instance.imageCache.clear();
  });

  group('#858 swiping the card back photos', () {
    final entry = WordEntry(
      id: 'w-apple',
      word: 'apple',
      pos: 'noun',
      meaning: '蘋果',
      createdAt: testNow,
      updatedAt: testNow,
    );
    late List<CardPhoto> photos;
    setUp(() {
      _run++;
      photos = [
        for (final id in ['p1', 'p2', 'p3', 'p4'])
          (_photo(id), const LabelPoint(0.4, 0.5), null),
      ];
    });

    Future<void> pumpBack(WidgetTester tester, List<int> picked) async {
      final repo =
          WordDatabaseRepository(clock: () => testNow, entries: [entry]);
      await pumpApp(tester,
          repository: repo,
          size: const Size(402, 2000),
          home: Scaffold(
              body: SingleChildScrollView(
                  child: FlashcardBack(
            entry: entry,
            card: const LearningCard(
                id: 'card', wordEntryId: 'w-apple', templateId: 't'),
            photo: photos.first.$1,
            anchor: photos.first.$2,
            photos: photos,
            onPhotoSelected: picked.add,
            template: repo.template,
            learnerLevel: 'A2',
            onPlay: () {},
            onOpen: () {},
          ))));
      await tester.pumpAndSettle();
    }

    /// Whether page [index]'s photo is in the image cache (loading or
    /// decoded) at the size the pager shows it.
    Future<bool> requested(WidgetTester tester, int index) async {
      final pager = tester.getSize(find.byType(PageView));
      final provider = photoProvider(photos[index].$1, null,
          photoPagerPageBox(pager, index, photos.length), 1)!;
      // Decoded at the page's size, far below the 4000 px original.
      expect(provider, isA<ResizeImage>());
      expect((provider as ResizeImage).width, lessThanOrEqualTo(512));
      final key = await provider.obtainKey(ImageConfiguration.empty);
      return PaintingBinding.instance.imageCache.statusForKey(key).tracked;
    }

    testWidgets('a swipe rebuilds only the dots, not the pages or the back',
        (tester) async {
      final picked = <int>[];
      await pumpBack(tester, picked);
      final meaning = tester.widget(find.text('名詞'));
      final firstPage =
          tester.widget(find.byType(PinnedPhoto, skipOffstage: false).first);
      expect(find.bySemanticsLabel(RegExp('第 1 張，共 4 張')), findsOneWidget);

      await tester.drag(find.byType(PageView), const Offset(-300, 0));
      await tester.pumpAndSettle();

      expect(picked, [1]);
      expect(find.bySemanticsLabel(RegExp('第 2 張，共 4 張')), findsOneWidget);
      // The same widget objects: neither the back's sections nor the page
      // left behind (still built beside the shown one) were built again.
      expect(identical(tester.widget(find.text('名詞')), meaning), isTrue);
      final pages =
          tester.widgetList(find.byType(PinnedPhoto, skipOffstage: false));
      expect(pages.any((w) => identical(w, firstPage)), isTrue);
    });

    testWidgets('the pages beside the settled one are decoded ahead, small',
        (tester) async {
      await pumpBack(tester, []);
      // Page 2 is not built yet (only the shown page and its neighbour
      // are), but it is already loading at its page's size.
      expect(await requested(tester, 1), isTrue);
      expect(await requested(tester, 2), isTrue);
      expect(await requested(tester, 3), isFalse);

      await tester.drag(find.byType(PageView), const Offset(-300, 0));
      await tester.pumpAndSettle();
      expect(await requested(tester, 3), isTrue);
    });

    test('the pager page box matches the pages\' insets', () {
      const frame = Size(362, 200);
      expect(photoPagerPageBox(frame, 0, 1), frame);
      expect(photoPagerPageBox(frame, 0, 3), const Size(358, 200));
      expect(photoPagerPageBox(frame, 1, 3), const Size(354, 200));
      expect(photoPagerPageBox(frame, 2, 3), const Size(358, 200));
    });
  });

  group('#859 photo disk cache', () {
    late Directory dir;
    setUp(() {
      dir = Directory.systemTemp.createTempSync('photo_cache_859');
      CachedNetworkPhoto.cacheDirectory = () async => dir;
    });
    tearDown(() async {
      await CachedNetworkPhoto.flushWrites();
      for (var i = 0; i < 10; i++) {
        try {
          if (dir.existsSync()) dir.deleteSync(recursive: true);
          return;
        } on FileSystemException {
          await Future<void>.delayed(const Duration(milliseconds: 40));
        }
      }
    });

    File cached(String url) => File(
        '${dir.path}${Platform.pathSeparator}${CachedNetworkPhoto.fileName(url)}');

    test('the second display of a URL makes no network request', () async {
      const url = 'https://photos.test/859/a.jpg';
      expect(await CachedNetworkPhoto.bytesFor(url), _png);
      await CachedNetworkPhoto.flushWrites();
      expect(await CachedNetworkPhoto.bytesFor(url), _png);
      expect(fetched, [url]);
    });

    test('the cache survives a restart (new provider, memory cleared)',
        () async {
      const url = 'https://photos.test/859/b.jpg';
      await CachedNetworkPhoto.bytesFor(url);
      await CachedNetworkPhoto.flushWrites();
      // What is lost when the app closes.
      CachedNetworkPhoto.releaseMemory();
      PaintingBinding.instance.imageCache.clear();
      fetched.clear();
      const again = CachedNetworkPhoto(url);
      expect(await CachedNetworkPhoto.bytesFor(again.url), _png);
      expect(fetched, isEmpty);
    });

    test('prefetch writes the photo to disk', () async {
      const url = 'https://photos.test/859/c.jpg';
      CachedNetworkPhoto.prefetch(url);
      for (var i = 0; i < 100 && !cached(url).existsSync(); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      await CachedNetworkPhoto.flushWrites();
      expect(cached(url).readAsBytesSync(), _png);
      expect(fetched, [url]);
    });

    test('#938 prefetch runs at most maxPrefetchParallel downloads', () async {
      var running = 0, peak = 0;
      final saved = CachedNetworkPhoto.fetch;
      CachedNetworkPhoto.fetch = (uri) async {
        peak = ++running > peak ? running : peak;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        running--;
        return _png;
      };
      addTearDown(() => CachedNetworkPhoto.fetch = saved);
      for (var i = 0; i < 12; i++) {
        CachedNetworkPhoto.prefetch('https://photos.test/938/$i.jpg');
      }
      await Future<void>.delayed(const Duration(milliseconds: 400));
      await CachedNetworkPhoto.flushWrites();
      expect(peak, lessThanOrEqualTo(CachedNetworkPhoto.maxPrefetchParallel));
      expect(peak, greaterThan(1));
    });

    test('pruning drops the least recently used file', () async {
      final urls = [
        for (final n in ['x', 'y', 'z']) 'https://photos.test/859/$n'
      ];
      for (final (i, url) in urls.indexed) {
        cached(url)
          ..writeAsBytesSync(_png)
          ..setLastModifiedSync(DateTime(2026, 1, 1 + i));
      }
      // x is the oldest download but was just shown again.
      await CachedNetworkPhoto.bytesFor(urls[0]);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      CachedNetworkPhoto.maxFiles = 2;
      await CachedNetworkPhoto.prune(dir);
      expect(cached(urls[0]).existsSync(), isTrue);
      expect(cached(urls[1]).existsSync(), isFalse);
      expect(cached(urls[2]).existsSync(), isTrue);
      expect(fetched, isEmpty);
    });
  });

  group('#859 server thumbnails', () {
    test('catalog pictures ask the server for its smaller copy', () {
      expect(sizedServerImage('https://api.test/api/image?id=7'),
          'https://api.test/api/image?id=7&w=$servedImageSide');
      expect(sizedServerImage('https://api.test/api/image?id=7&w=512'),
          'https://api.test/api/image?id=7&w=512');
      expect(sizedServerImage('https://photos.test/a.jpg'),
          'https://photos.test/a.jpg');
    });
  });
}
