import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../models/models.dart';
import 'config_service.dart';

class LabelService {
  static const Duration timeout = Duration(seconds: 60);

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
        Label(en: 'coffee', zh: '咖啡', confidence: 0.95),
        Label(en: 'cup', zh: '杯子', confidence: 0.92),
        Label(en: 'table', zh: '桌子', confidence: 0.88),
        Label(en: 'morning', zh: '早晨', confidence: 0.75),
        Label(en: 'drink', zh: '飲料', confidence: 0.70),
      ],
      model: 'mock-v1',
      latencyMs: 800,
    );
  }

  static Future<LabelResponse> _getLiveLabels(Uint8List imageBytes) async {
    try {
      final uri = Uri.parse(ConfigService.labelEndpoint);
      final request = http.MultipartRequest('POST', uri);

      request.headers.addAll(ConfigService.authHeaders);

      request.files.add(http.MultipartFile.fromBytes(
        'image',
        imageBytes,
        filename: 'photo.jpg',
      ));

      final streamedResponse = await request.send().timeout(timeout);
      final response = await http.Response.fromStream(streamedResponse);

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
