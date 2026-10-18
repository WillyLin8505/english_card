import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/widgets/mobile/photo_cache.dart';

import 'helpers.dart';

// Card #252: photos are decoded at the size they are shown and their
// bytes / decoded images are cached.

Photo _photo({int? width, int? height, String? storedKey, String? url}) =>
    Photo(
        id: 'p',
        title: 'p',
        takenAt: testNow,
        createdAt: testNow,
        storedKey: storedKey,
        networkUrl: url,
        width: width,
        height: height);

void main() {
  group('decode width', () {
    test('a 12 MP photo on the card back decodes at ~1/4 of its width', () {
      // Card back: ~350 × 200 at 3×; a 4032 × 3024 phone photo covers it
      // at 1050 px wide → the 1536 bucket, not 4032.
      final w = photoDecodeWidth(
          _photo(width: 4032, height: 3024), const Size(350, 200), 3)!;
      expect(w, 1536);
      expect(w * w * 3024 / 4032 * 4 / 1e6, lessThan(8)); // < 8 MB decoded
    });

    test('album thumbnails decode small; contain uses the smaller scale', () {
      expect(
          photoDecodeWidth(
              _photo(width: 4032, height: 3024), const Size(110, 110), 2),
          384);
      expect(
          photoDecodeWidth(
              _photo(width: 4000, height: 1000), const Size(300, 300), 1,
              fit: BoxFit.contain),
          384);
    });

    test('unknown size covers either way; huge boxes cap at 2048', () {
      expect(photoDecodeWidth(_photo(), const Size(200, 100), 1), 384);
      expect(
          photoDecodeWidth(
              _photo(width: 9000, height: 9000), const Size(2000, 2000), 3),
          2048);
      expect(photoDecodeWidth(_photo(), Size.infinite, 1), isNull);
    });

    test('near-equal boxes share a cache entry (precache matches)', () {
      final p = _photo(width: 1600, height: 1200);
      expect(photoProvider(p, null, const Size(320, 200), 3),
          photoProvider(p, null, const Size(340, 200), 3));
    });
  });

  test('stored photos have a stable cache key', () {
    final store = PhotoStore.inMemory();
    expect(StoredPhotoImage(store, 'a'), StoredPhotoImage(store, 'a'));
    expect(StoredPhotoImage(store, 'a'), isNot(StoredPhotoImage(store, 'b')));
    expect(StoredPhotoImage(store, 'a'),
        isNot(StoredPhotoImage(PhotoStore.inMemory(), 'a')));
    // Before: MemoryImage(bytes) — a new key for every read of the same photo.
    final bytes = Uint8List.fromList([1, 2, 3]);
    expect(MemoryImage(bytes), isNot(MemoryImage(Uint8List.fromList(bytes))));
  });

  group('network bytes on disk', () {
    late Directory dir;
    late int fetches;
    setUp(() async {
      dir = await Directory.systemTemp.createTemp('photo_cache_test');
      fetches = 0;
      CachedNetworkPhoto.cacheDirectory = () async => dir;
      CachedNetworkPhoto.fetch = (uri) async {
        fetches++;
        return Uint8List.fromList(uri.toString().codeUnits);
      };
    });
    tearDown(() => dir.delete(recursive: true));

    test('downloaded once, then read from disk', () async {
      const url = 'https://example.com/a.jpg';
      final first = await CachedNetworkPhoto.bytesFor(url);
      // The write is not awaited by the loader.
      for (var i = 0; i < 50 && !await _cached(dir); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      final second = await CachedNetworkPhoto.bytesFor(url);
      expect(fetches, 1);
      expect(second, first);
      expect(CachedNetworkPhoto.fileName(url),
          CachedNetworkPhoto.fileName(url));
      expect(CachedNetworkPhoto.fileName(url),
          isNot(CachedNetworkPhoto.fileName('$url?x')));
    });

    test('a failed download is not cached', () async {
      CachedNetworkPhoto.fetch = (uri) async {
        fetches++;
        throw const HttpException('offline');
      };
      await expectLater(
          CachedNetworkPhoto.bytesFor('https://example.com/b.jpg'),
          throwsA(isA<HttpException>()));
      expect(await _cached(dir), isFalse);
    });
  });

  // 修前／修後 numbers for result.md: decoding a phone-size photo whole vs
  // at the card back's width.
  testWidgets('measure: full decode vs decode at shown size', (tester) async {
    await tester.runAsync(() async {
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      for (var i = 0; i < 40; i++) {
        canvas.drawRect(Rect.fromLTWH(i * 100.0, 0, 100, 3024),
            Paint()..color = Color(0xFF000000 | (i * 0x061f3d)));
      }
      final big = await recorder.endRecording().toImage(4032, 3024);
      final png = (await big.toByteData(format: ui.ImageByteFormat.png))!
          .buffer
          .asUint8List();
      Future<(int, int)> decode(int? width) async {
        final watch = Stopwatch()..start();
        final codec = await ui.instantiateImageCodec(png, targetWidth: width);
        final frame = await codec.getNextFrame();
        watch.stop();
        final bytes = frame.image.width * frame.image.height * 4;
        frame.image.dispose();
        return (watch.elapsedMilliseconds, bytes);
      }

      Future<(int, int)> best(int? width) async {
        var r = await decode(width);
        for (var i = 0; i < 2; i++) {
          final n = await decode(width);
          if (n.$1 < r.$1) r = n;
        }
        return r;
      }

      final shownWidth = photoDecodeWidth(
          _photo(width: 4032, height: 3024), const Size(350, 200), 3);
      await decode(shownWidth); // warm-up
      final full = await best(null);
      final shown = await best(shownWidth);
      // ignore: avoid_print
      print('card252 decode full: ${full.$1} ms, ${full.$2 ~/ 1000000} MB; '
          'shown: ${shown.$1} ms, ${shown.$2 ~/ 1000000} MB; photos in a '
          '100 MB ImageCache: ${100000000 ~/ full.$2} vs ${100000000 ~/ shown.$2}');
      expect(shown.$2 * 6, lessThan(full.$2));
    });
  });
}

Future<bool> _cached(Directory dir) async =>
    await dir.list().any((f) => f.path.endsWith('.img'));
