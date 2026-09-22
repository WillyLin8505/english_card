import 'package:flutter_test/flutter_test.dart';
import 'package:english_card/models/models.dart';

void main() {
  group('LabelResponse', () {
    test('should parse success response with all fields', () {
      final json = {
        'ok': true,
        'labels': [
          {'en': 'cup', 'zh': '杯子', 'confidence': 0.91},
          {'en': 'table', 'zh': '桌子', 'confidence': 0.85},
        ],
        'model': 'gpt-4o-mini',
        'latency_ms': 1234,
      };

      final response = LabelResponse.fromJson(json);

      expect(response.ok, isTrue);
      expect(response.labels, isNotNull);
      expect(response.labels!.length, equals(2));
      expect(response.labels![0].en, equals('cup'));
      expect(response.labels![0].zh, equals('杯子'));
      expect(response.labels![0].confidence, equals(0.91));
      expect(response.model, equals('gpt-4o-mini'));
      expect(response.latencyMs, equals(1234));
      expect(response.error, isNull);
    });

    test('should parse success response with minimal fields', () {
      final json = {
        'ok': true,
        'labels': [
          {'en': 'cup'},
        ],
      };

      final response = LabelResponse.fromJson(json);

      expect(response.ok, isTrue);
      expect(response.labels!.length, equals(1));
      expect(response.labels![0].en, equals('cup'));
      expect(response.labels![0].zh, isNull);
      expect(response.labels![0].confidence, isNull);
    });

    test('should parse error response', () {
      final json = {
        'ok': false,
        'error': {
          'code': 'timeout',
          'message': 'Request timed out',
        },
      };

      final response = LabelResponse.fromJson(json);

      expect(response.ok, isFalse);
      expect(response.labels, isNull);
      expect(response.error, isNotNull);
      expect(response.error!.code, equals('timeout'));
      expect(response.error!.message, equals('Request timed out'));
    });
  });

  group('LabelError', () {
    test('should provide localized message for timeout', () {
      final error = LabelError(code: 'timeout', message: 'Request timed out');
      expect(error.localizedMessage, equals('請求逾時，請稍後再試'));
    });

    test('should provide localized message for upstream', () {
      final error = LabelError(code: 'upstream', message: 'Upstream error');
      expect(error.localizedMessage, equals('上游服務錯誤，請稍後再試'));
    });

    test('should provide localized message for bad_image', () {
      final error = LabelError(code: 'bad_image', message: 'Invalid image');
      expect(error.localizedMessage, equals('圖片格式錯誤，請選擇其他照片'));
    });

    test('should provide localized message for queue_full', () {
      final error = LabelError(code: 'queue_full', message: 'Queue is full');
      expect(error.localizedMessage, equals('伺服器繁忙，請稍後再試'));
    });

    test('should provide localized message for unavailable', () {
      final error = LabelError(code: 'unavailable', message: 'Service unavailable');
      expect(error.localizedMessage, equals('服務暫時不可用，請稍後再試'));
    });

    test('should use message for unknown code', () {
      final error = LabelError(code: 'custom_error', message: 'Custom error message');
      expect(error.localizedMessage, equals('Custom error message'));
    });

    test('should show code when message is empty for unknown code', () {
      final error = LabelError(code: 'mystery', message: '');
      expect(error.localizedMessage, equals('發生錯誤（mystery）'));
    });
  });

  group('Label', () {
    test('should serialize to JSON correctly', () {
      final label = Label(en: 'cup', zh: '杯子', confidence: 0.91);
      final json = label.toJson();

      expect(json['en'], equals('cup'));
      expect(json['zh'], equals('杯子'));
      expect(json['confidence'], equals(0.91));
    });

    test('should omit null fields in JSON', () {
      final label = Label(en: 'cup');
      final json = label.toJson();

      expect(json['en'], equals('cup'));
      expect(json.containsKey('zh'), isFalse);
      expect(json.containsKey('confidence'), isFalse);
    });

    test('should copy with new values', () {
      final original = Label(en: 'cup', zh: '杯子', confidence: 0.91);
      final copied = original.copyWith(en: 'mug', zh: '馬克杯');

      expect(copied.en, equals('mug'));
      expect(copied.zh, equals('馬克杯'));
      expect(copied.confidence, equals(0.91));
    });
  });
}
