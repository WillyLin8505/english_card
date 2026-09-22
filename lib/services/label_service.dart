import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import '../models/models.dart';
import 'config_service.dart';

enum LabelRequestEncoding { rawJpeg, multipart }

class LabelService {
  static const Duration timeout = Duration(seconds: 60);

  static LabelRequestEncoding get requestEncoding =>
      kIsWeb ? LabelRequestEncoding.rawJpeg : LabelRequestEncoding.multipart;

  static Future<LabelResponse> getLabels(Uint8List imageBytes) async {
    if (ConfigService.shouldUseMock) {
      return _getMockLabels();
    }
    return _getLiveLabels(imageBytes);
  }

  static Future<LabelResponse> _getMockLabels() async {
    await Future.delayed(const Duration(milliseconds: 800));

    return LabelResponse(
      ok: true,
      labels: [
        Label(
          en: 'coffee',
          zh: '咖啡',
          ipa: '/ˈkɔːfi/',
          confidence: 0.95,
          examples: [
            ExampleSentence(en: 'I need a cup of coffee to wake up.', zh: '我需要一杯咖啡來提神。'),
            ExampleSentence(en: 'This coffee smells amazing.', zh: '這咖啡聞起來很香。'),
          ],
          phrases: [
            Phrase(en: 'coffee break', zh: '咖啡休息時間'),
            Phrase(en: 'black coffee', zh: '黑咖啡'),
          ],
        ),
        Label(
          en: 'cup',
          zh: '杯子',
          ipa: '/kʌp/',
          confidence: 0.92,
          examples: [
            ExampleSentence(en: 'Please pass me that cup.', zh: '請把那個杯子遞給我。'),
            ExampleSentence(en: 'The cup is half full.', zh: '杯子裡有半杯水。'),
          ],
          phrases: [
            Phrase(en: 'a cup of tea', zh: '一杯茶'),
            Phrase(en: 'cup holder', zh: '杯架'),
          ],
        ),
        Label(
          en: 'table',
          zh: '桌子',
          ipa: '/ˈteɪbl/',
          confidence: 0.88,
          examples: [
            ExampleSentence(en: 'Put the book on the table.', zh: '把書放在桌上。'),
            ExampleSentence(en: 'We sat around the table.', zh: '我們圍著桌子坐。'),
          ],
          phrases: [
            Phrase(en: 'coffee table', zh: '茶几'),
            Phrase(en: 'table manners', zh: '餐桌禮儀'),
          ],
        ),
        Label(
          en: 'morning',
          zh: '早晨',
          ipa: '/ˈmɔːrnɪŋ/',
          confidence: 0.75,
          examples: [
            ExampleSentence(en: 'Good morning!', zh: '早安！'),
            ExampleSentence(en: 'I exercise every morning.', zh: '我每天早上運動。'),
          ],
          phrases: [
            Phrase(en: 'morning person', zh: '早起的人'),
            Phrase(en: 'tomorrow morning', zh: '明天早上'),
          ],
        ),
        Label(
          en: 'drink',
          zh: '飲料',
          ipa: '/drɪŋk/',
          confidence: 0.70,
          examples: [
            ExampleSentence(en: 'Would you like something to drink?', zh: '你想喝點什麼嗎？'),
            ExampleSentence(en: 'This is my favorite drink.', zh: '這是我最愛的飲料。'),
          ],
          phrases: [
            Phrase(en: 'soft drink', zh: '軟性飲料'),
            Phrase(en: 'drink up', zh: '喝光'),
          ],
        ),
      ],
      model: 'mock-v1',
      latencyMs: 800,
    );
  }

  static Future<LabelResponse> _getLiveLabels(Uint8List imageBytes) async {
    try {
      final uri = Uri.parse(ConfigService.labelEndpoint);
      final http.Response response;

      if (requestEncoding == LabelRequestEncoding.rawJpeg) {
        response = await _postRawJpeg(uri, imageBytes);
      } else {
        response = await _postMultipart(uri, imageBytes);
      }

      return _parseResponse(response);
    } on TimeoutException {
      return LabelResponse(
        ok: false,
        error: LabelError(code: 'timeout', message: '請求逾時'),
      );
    } catch (e) {
      return LabelResponse(
        ok: false,
        error: LabelError(code: 'network', message: '網路錯誤：$e'),
      );
    }
  }

  static Future<http.Response> _postRawJpeg(Uri uri, Uint8List imageBytes) async {
    return await http.post(
      uri,
      headers: {
        ...ConfigService.authHeaders,
        'Content-Type': 'image/jpeg',
      },
      body: imageBytes,
    ).timeout(timeout);
  }

  static Future<http.Response> _postMultipart(Uri uri, Uint8List imageBytes) async {
    final request = http.MultipartRequest('POST', uri);
    request.headers.addAll(ConfigService.authHeaders);
    request.files.add(http.MultipartFile.fromBytes(
      'image',
      imageBytes,
      filename: 'photo.jpg',
    ));

    final streamedResponse = await request.send().timeout(timeout);
    return await http.Response.fromStream(streamedResponse);
  }

  static LabelResponse _parseResponse(http.Response response) {
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return LabelResponse.fromJson(json);
    } else {
      try {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return LabelResponse.fromJson(json);
      } catch (_) {
        return LabelResponse(
          ok: false,
          error: LabelError(
            code: 'http_${response.statusCode}',
            message: 'HTTP 錯誤 ${response.statusCode}',
          ),
        );
      }
    }
  }

  static Future<bool> checkHealth() async {
    if (ConfigService.shouldUseMock) {
      return true;
    }

    try {
      final uri = Uri.parse(ConfigService.healthEndpoint);
      final response = await http.get(uri, headers: ConfigService.authHeaders)
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return json['ok'] == true;
      }
      return false;
    } catch (_) {
      return false;
    }
  }
}
