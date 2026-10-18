import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

class DeferredPhotoStore extends PhotoStore {
  DeferredPhotoStore() : super.inMemory();
  final reads = <String>[];
  final pending = <String, Completer<Uint8List?>>{};
  @override
  Future<Uint8List?> storedBytes(String key) {
    reads.add(key);
    return pending.putIfAbsent(key, Completer<Uint8List?>.new).future;
  }
}

Photo storedPhoto(String key) => Photo(
    id: key, title: key, takenAt: testNow, createdAt: testNow, storedKey: key);

void main() {
  test(
      'legacy eager box reopens lazily without changing original bytes or keys',
      () async {
    final dir = await Directory.systemTemp.createTemp('photo_lazy_test');
    try {
      Hive.init(dir.path);
      final legacy = await Hive.openBox<Uint8List>('wd_photo_bytes');
      final bytes = Uint8List.fromList([0, 1, 127, 255]);
      await legacy.put('existing-photo', bytes);
      await legacy.close();
      var box = await Hive.openLazyBox<Uint8List>('wd_photo_bytes');
      var store = PhotoStore.fromLazyBox(box);
      expect(box.keys, ['existing-photo']);
      expect(await store.storedBytes('existing-photo'), bytes);
      expect(await store.storedBytes('missing'), isNull);
      expect((await store.save('new-photo', bytes)).storedKey, 'new-photo');
      await box.close();
      box = await Hive.openLazyBox<Uint8List>('wd_photo_bytes');
      store = PhotoStore.fromLazyBox(box);
      expect(await store.storedBytes('existing-photo'), bytes);
      expect(await store.storedBytes('new-photo'), bytes);
    } finally {
      await Hive.close();
      await dir.delete(recursive: true);
    }
  });

  testWidgets(
      'read once per visible key, hide stale pixels while changing photos',
      (tester) async {
    final store = DeferredPhotoStore();
    var key = 'first';
    late StateSetter rebuild;
    await pumpApp(tester, photoStore: store, home: StatefulBuilder(
      builder: (context, setState) {
        rebuild = setState;
        return SizedBox(
            width: 200, height: 200, child: PhotoImage(storedPhoto(key)));
      },
    ));
    // Pixels shown, or null while the placeholder holds the place.
    Object? pixels() => tester.widget<RawImage>(find.byType(RawImage)).image;
    Future<void> decode() async {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 200)));
      await tester.pump();
    }

    expect(store.reads, ['first']);
    expect(pixels(), isNull);
    rebuild(() {});
    await tester.pump();
    expect(store.reads, ['first']);
    final data = await rootBundle.load('assets/sample/photo_kitchen.jpg');
    store.pending['first']!.complete(data.buffer.asUint8List());
    await decode();
    expect(pixels(), isNotNull);
    rebuild(() => key = 'second');
    await tester.pump();
    expect(store.reads, ['first', 'second']);
    expect(pixels(), isNull);
    store.pending['second']!.complete(data.buffer.asUint8List());
    await decode();
    expect(pixels(), isNotNull);
    // Back to the first photo: decoded once, kept in the ImageCache — no
    // second read (card #252: it used to be reread and decoded every mount).
    rebuild(() => key = 'first');
    await tester.pump();
    expect(store.reads, ['first', 'second']);
    expect(pixels(), isNotNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('storage failure uses the existing photo error UI',
      (tester) async {
    final store = DeferredPhotoStore();
    await pumpApp(tester,
        photoStore: store,
        home: PhotoImage(storedPhoto('bad'),
            imageErrorBuilder: (_) => const Text('照片暫時無法載入')));
    store.pending['bad']!.completeError(StateError('read failed'));
    await tester.pump();
    await tester.pump();
    expect(find.text('照片暫時無法載入'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

