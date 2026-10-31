import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/services/rating_prompt.dart';

void main() {
  late int calls;
  late RatingPrompt p;
  final day0 = DateTime(2026, 10, 1, 10);

  setUp(() {
    calls = 0;
    p = RatingPrompt.forTest(null, () async => calls++);
  });

  test('not on first use or before 7 days', () async {
    await p.noteUse(day0);
    expect(await p.onReviewCompleted(day0), isFalse);
    await p.noteUse(day0.add(const Duration(days: 1)));
    await p.noteUse(day0.add(const Duration(days: 2)));
    expect(
        await p.onReviewCompleted(day0.add(const Duration(days: 6))), isFalse);
    expect(calls, 0);
  });

  test('not when used on fewer than 3 days', () async {
    await p.noteUse(day0);
    expect(
        await p.onReviewCompleted(day0.add(const Duration(days: 8))), isFalse);
    expect(calls, 0); // days used: day 0 and day 8 only
  });

  test('asks after 7 days and 3 active days, once per version', () async {
    await p.noteUse(day0);
    await p.noteUse(day0.add(const Duration(days: 3)));
    final t = day0.add(const Duration(days: 8));
    expect(await p.onReviewCompleted(t), isTrue);
    expect(calls, 1);
    expect(await p.onReviewCompleted(t.add(const Duration(days: 1))), isFalse);
    expect(calls, 1);
  });

  test('state survives restart', () async {
    final dir = await Directory.systemTemp.createTemp('rp915');
    Hive.init(dir.path);
    final box = await Hive.openBox<String>('rating_prompt');
    final a = RatingPrompt.forTest(box, () async => calls++);
    await a.noteUse(day0);
    await a.noteUse(day0.add(const Duration(days: 3)));
    final b = RatingPrompt.forTest(box, () async => calls++);
    expect(
        await b.onReviewCompleted(day0.add(const Duration(days: 8))), isTrue);
    final c = RatingPrompt.forTest(box, () async => calls++);
    expect(
        await c.onReviewCompleted(day0.add(const Duration(days: 9))), isFalse);
    expect(calls, 1);
    await box.close();
  });
}
