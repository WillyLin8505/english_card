import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:english_card/models/models.dart';

void main() {
  group('AlbumEntry', () {
    test('should serialize to JSON correctly', () {
      final entry = AlbumEntry(
        id: 'test-id-123',
        createdAt: DateTime(2024, 1, 15, 10, 30),
        imagePath: '/path/to/image.jpg',
        labels: [
          Label(en: 'cup', zh: '杯子', confidence: 0.95),
          Label(en: 'table', zh: '桌子', confidence: 0.88),
        ],
      );

      final json = entry.toJson();

      expect(json['id'], equals('test-id-123'));
      expect(json['created_at'], equals('2024-01-15T10:30:00.000'));
      expect(json['image_path'], equals('/path/to/image.jpg'));
      expect(json['labels'], isA<List>());
      expect(json['labels'].length, equals(2));
    });

    test('should deserialize from JSON correctly', () {
      final json = {
        'id': 'test-id-456',
        'created_at': '2024-02-20T14:45:00.000',
        'image_path': '/another/path.jpg',
        'labels': [
          {'en': 'coffee', 'zh': '咖啡', 'confidence': 0.92},
        ],
      };

      final entry = AlbumEntry.fromJson(json);

      expect(entry.id, equals('test-id-456'));
      expect(entry.createdAt.year, equals(2024));
      expect(entry.createdAt.month, equals(2));
      expect(entry.createdAt.day, equals(20));
      expect(entry.imagePath, equals('/another/path.jpg'));
      expect(entry.labels.length, equals(1));
      expect(entry.labels[0].en, equals('coffee'));
      expect(entry.labels[0].zh, equals('咖啡'));
    });

    test('should round-trip JSON correctly', () {
      final original = AlbumEntry(
        id: 'roundtrip-id',
        createdAt: DateTime(2024, 3, 10, 9, 15),
        imagePath: '/test/roundtrip.jpg',
        labels: [
          Label(en: 'phone', zh: '手機', confidence: 0.99),
          Label(en: 'screen'),
        ],
      );

      final jsonString = jsonEncode(original.toJson());
      final restored = AlbumEntry.fromJson(jsonDecode(jsonString));

      expect(restored.id, equals(original.id));
      expect(restored.createdAt, equals(original.createdAt));
      expect(restored.imagePath, equals(original.imagePath));
      expect(restored.labels.length, equals(original.labels.length));
      expect(restored.labels[0].en, equals(original.labels[0].en));
      expect(restored.labels[1].en, equals(original.labels[1].en));
    });

    test('should copy with new labels', () {
      final original = AlbumEntry(
        id: 'copy-test',
        createdAt: DateTime.now(),
        imagePath: '/test/copy.jpg',
        labels: [Label(en: 'old')],
      );

      final newLabels = [Label(en: 'new', zh: '新')];
      final copied = original.copyWith(labels: newLabels);

      expect(copied.id, equals(original.id));
      expect(copied.imagePath, equals(original.imagePath));
      expect(copied.labels.length, equals(1));
      expect(copied.labels[0].en, equals('new'));
      expect(copied.labels[0].zh, equals('新'));
    });

    test('should handle empty labels list', () {
      final entry = AlbumEntry(
        id: 'empty-labels',
        createdAt: DateTime.now(),
        imagePath: '/test/empty.jpg',
        labels: [],
      );

      final json = entry.toJson();
      expect(json['labels'], isEmpty);

      final restored = AlbumEntry.fromJson(json);
      expect(restored.labels, isEmpty);
    });

    test('should handle null labels in JSON', () {
      final json = {
        'id': 'null-labels',
        'created_at': '2024-01-01T00:00:00.000',
        'image_path': '/test.jpg',
        'labels': null,
      };

      final entry = AlbumEntry.fromJson(json);
      expect(entry.labels, isEmpty);
    });
  });

  group('Label editing', () {
    test('should update label en field', () {
      final label = Label(en: 'cup', zh: '杯子', confidence: 0.9);
      final updated = label.copyWith(en: 'mug');

      expect(updated.en, equals('mug'));
      expect(updated.zh, equals('杯子'));
      expect(updated.confidence, equals(0.9));
    });

    test('should update label zh field', () {
      final label = Label(en: 'cup', zh: '杯子');
      final updated = label.copyWith(zh: '茶杯');

      expect(updated.en, equals('cup'));
      expect(updated.zh, equals('茶杯'));
    });

    test('should preserve unchanged fields', () {
      final label = Label(en: 'coffee', zh: '咖啡', confidence: 0.95);
      final updated = label.copyWith();

      expect(updated.en, equals(label.en));
      expect(updated.zh, equals(label.zh));
      expect(updated.confidence, equals(label.confidence));
    });
  });
}
