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

    test('should parse label with ipa and examples', () {
      final json = {
        'en': 'coffee',
        'zh': '咖啡',
        'ipa': '/ˈkɔːfi/',
        'confidence': 0.95,
        'examples': [
          {'en': 'I love coffee.', 'zh': '我愛咖啡。'},
          {'en': 'Coffee is hot.', 'zh': '咖啡很燙。'},
        ],
      };

      final label = Label.fromJson(json);

      expect(label.en, equals('coffee'));
      expect(label.zh, equals('咖啡'));
      expect(label.ipa, equals('/ˈkɔːfi/'));
      expect(label.confidence, equals(0.95));
      expect(label.examples.length, equals(2));
      expect(label.examples[0].en, equals('I love coffee.'));
      expect(label.examples[0].zh, equals('我愛咖啡。'));
    });

    test('should serialize label with ipa and examples', () {
      final label = Label(
        en: 'cup',
        zh: '杯子',
        ipa: '/kʌp/',
        confidence: 0.92,
        examples: [
          ExampleSentence(en: 'A cup of tea.', zh: '一杯茶。'),
        ],
      );

      final json = label.toJson();

      expect(json['en'], equals('cup'));
      expect(json['ipa'], equals('/kʌp/'));
      expect(json['examples'], isA<List>());
      expect(json['examples'].length, equals(1));
      expect(json['examples'][0]['en'], equals('A cup of tea.'));
    });

    test('should handle missing ipa and examples gracefully', () {
      final json = {'en': 'table', 'zh': '桌子'};
      final label = Label.fromJson(json);

      expect(label.en, equals('table'));
      expect(label.ipa, isNull);
      expect(label.examples, isEmpty);
    });

    test('should copy with new ipa', () {
      final original = Label(en: 'cup', ipa: '/kʌp/');
      final copied = original.copyWith(ipa: '/kəp/');

      expect(copied.ipa, equals('/kəp/'));
    });
  });

  group('ExampleSentence', () {
    test('should parse from JSON', () {
      final json = {'en': 'Hello world.', 'zh': '你好世界。'};
      final example = ExampleSentence.fromJson(json);

      expect(example.en, equals('Hello world.'));
      expect(example.zh, equals('你好世界。'));
    });

    test('should serialize to JSON', () {
      final example = ExampleSentence(en: 'Test sentence.', zh: '測試句子。');
      final json = example.toJson();

      expect(json['en'], equals('Test sentence.'));
      expect(json['zh'], equals('測試句子。'));
    });

    test('should handle missing fields with defaults', () {
      final json = <String, dynamic>{};
      final example = ExampleSentence.fromJson(json);

      expect(example.en, equals(''));
      expect(example.zh, equals(''));
    });
  });

  group('Phrase', () {
    test('should parse from JSON', () {
      final json = {'en': 'coffee break', 'zh': '咖啡休息時間'};
      final phrase = Phrase.fromJson(json);

      expect(phrase.en, equals('coffee break'));
      expect(phrase.zh, equals('咖啡休息時間'));
    });

    test('should serialize to JSON', () {
      final phrase = Phrase(en: 'black coffee', zh: '黑咖啡');
      final json = phrase.toJson();

      expect(json['en'], equals('black coffee'));
      expect(json['zh'], equals('黑咖啡'));
    });

    test('should handle missing fields with defaults', () {
      final json = <String, dynamic>{};
      final phrase = Phrase.fromJson(json);

      expect(phrase.en, equals(''));
      expect(phrase.zh, equals(''));
    });

    test('should support equality', () {
      final phrase1 = Phrase(en: 'test', zh: '測試');
      final phrase2 = Phrase(en: 'test', zh: '測試');
      final phrase3 = Phrase(en: 'other', zh: '其他');

      expect(phrase1 == phrase2, isTrue);
      expect(phrase1 == phrase3, isFalse);
    });
  });

  group('Label with phrases', () {
    test('should parse label with phrases', () {
      final json = {
        'en': 'coffee',
        'zh': '咖啡',
        'ipa': '/ˈkɔːfi/',
        'examples': [
          {'en': 'I love coffee.', 'zh': '我愛咖啡。'},
        ],
        'phrases': [
          {'en': 'coffee break', 'zh': '咖啡休息時間'},
          {'en': 'black coffee', 'zh': '黑咖啡'},
        ],
      };

      final label = Label.fromJson(json);

      expect(label.phrases.length, equals(2));
      expect(label.phrases[0].en, equals('coffee break'));
      expect(label.phrases[0].zh, equals('咖啡休息時間'));
      expect(label.phrases[1].en, equals('black coffee'));
    });

    test('should serialize label with phrases', () {
      final label = Label(
        en: 'cup',
        zh: '杯子',
        phrases: [
          Phrase(en: 'a cup of tea', zh: '一杯茶'),
        ],
      );

      final json = label.toJson();

      expect(json['phrases'], isA<List>());
      expect(json['phrases'].length, equals(1));
      expect(json['phrases'][0]['en'], equals('a cup of tea'));
    });

    test('should handle missing phrases gracefully', () {
      final json = {'en': 'table', 'zh': '桌子'};
      final label = Label.fromJson(json);

      expect(label.phrases, isEmpty);
    });

    test('should omit empty phrases in JSON', () {
      final label = Label(en: 'cup');
      final json = label.toJson();

      expect(json.containsKey('phrases'), isFalse);
    });

    test('should copy with new phrases', () {
      final original = Label(en: 'cup');
      final copied = original.copyWith(
        phrases: [Phrase(en: 'cup holder', zh: '杯架')],
      );

      expect(copied.phrases.length, equals(1));
      expect(copied.phrases[0].en, equals('cup holder'));
    });
  });
}
