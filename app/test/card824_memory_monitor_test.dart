import 'dart:async';

import 'package:flutter/painting.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/card_report.dart';
import 'package:photo_english_app/services/memory_monitor.dart';

/// 問題回報 #824: memory reports through the 意見回饋 path, one per screen
/// per day, and caches dropped on a memory warning.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/memory');
  const mb = 1024 * 1024;
  late int available;
  late DateTime now;
  late String page;
  late CardReportService service;
  late MemoryMonitor monitor;

  setUp(() {
    available = 1500 * mb;
    now = DateTime(2026, 10, 27, 21, 0);
    page = '相片冊';
    service = CardReportService(remote: false, persist: false);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      switch (call.method) {
        case 'snapshot':
          return {'available': available, 'footprint': 900 * mb};
        case 'device':
          return {'model': 'iPhone13,2', 'system': '18.1'};
      }
      return null;
    });
    monitor = MemoryMonitor(
      channel: channel,
      service: service,
      now: () => now,
      log: MemoryReportLogInMemory(),
      page: () => page,
      enabled: true,
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('snapshot reads the channel numbers', () async {
    final snap = await monitor.snapshot();
    expect(snap!.footprintMb, 900);
    expect(snap.availableMb, 1500);
  });

  test('plenty left: no report', () async {
    expect(await monitor.check(), isFalse);
    expect(service.pendingCount, 0);
  });

  test('below the threshold: one report per screen per day', () async {
    available = 250 * mb;
    expect(await monitor.check(), isTrue);
    expect(service.pendingCount, 1);
    final record = (await service.history()).single;
    expect(record.title, '[記憶體] 相片冊');

    // Same screen, same day: nothing more.
    expect(await monitor.check(), isFalse);
    expect(service.pendingCount, 1);

    // Another screen reports once; the next day the first one may again.
    page = '複習';
    expect(await monitor.check(), isTrue);
    now = now.add(const Duration(days: 1));
    page = '相片冊';
    expect(await monitor.check(), isTrue);
    expect(service.pendingCount, 3);
  });

  test('the simulator (no limit) never crosses the threshold', () async {
    available = 0;
    expect(await monitor.check(), isFalse);
  });

  test('report detail carries device, screen and numbers', () {
    final issue = memoryIssue(
        page: '單字本',
        warning: false,
        snap: const MemorySnapshot(available: 250 * mb, footprint: 1800 * mb),
        model: 'iPhone13,2',
        system: '18.1');
    final detail = issue['detail'] as String;
    expect(issue['title'], '[記憶體] 單字本');
    expect(detail, contains('裝置型號：iPhone13,2'));
    expect(detail, contains('iOS 版本：18.1'));
    expect(detail, contains('畫面：單字本'));
    expect(detail, contains('App 佔用：1800 MB'));
    expect(detail, contains('剩餘可用：250 MB'));
    expect(detail, contains('低於 300 MB'));
  });

  test('a memory warning clears caches and reports once', () async {
    var released = 0;
    monitor.addReleaser(() => released++);
    final images = PaintingBinding.instance.imageCache;
    images.putIfAbsent(
        'k', () => OneFrameImageStreamCompleter(Completer<ImageInfo>().future));
    expect(images.pendingImageCount + images.currentSize, greaterThan(0));

    expect(await monitor.onMemoryWarning(), isTrue);
    expect(released, 1);
    expect(images.pendingImageCount + images.currentSize, 0);
    final issue = (await service.history()).single;
    expect(issue.title, '[記憶體] 相片冊');

    // Caches still dropped on a second warning, but no second report.
    expect(await monitor.onMemoryWarning(), isFalse);
    expect(released, 2);
    expect(service.pendingCount, 1);
  });

  test('no channel (web, Android, tests): nothing happens', () async {
    final off = MemoryMonitor(
        channel: const MethodChannel('test/memory-missing'),
        service: service,
        log: MemoryReportLogInMemory(),
        enabled: true);
    expect(await off.snapshot(), isNull);
    expect(await off.check(), isFalse);
    expect(await off.onMemoryWarning(), isFalse);
    await off.start();
    expect(off.running, isFalse);
    expect(service.pendingCount, 0);

    final android = MemoryMonitor(
        channel: channel, service: service, log: MemoryReportLogInMemory());
    await android.start();
    expect(android.running, isFalse);
  });
}
