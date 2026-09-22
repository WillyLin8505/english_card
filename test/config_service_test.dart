import 'package:flutter_test/flutter_test.dart';
import 'package:english_card/services/config_service.dart';

void main() {
  group('ConfigService', () {
    test('default values should enable mock mode', () {
      expect(ConfigService.shouldUseMock, isTrue);
    });

    test('configSummary should show Mock mode when using mock', () {
      if (ConfigService.shouldUseMock) {
        expect(ConfigService.configSummary, equals('Mock 模式'));
      }
    });

    test('labelEndpoint should append /v1/label to base', () {
      if (ConfigService.labelApiBase.isNotEmpty) {
        expect(
          ConfigService.labelEndpoint,
          equals('${ConfigService.labelApiBase}/v1/label'),
        );
      }
    });

    test('healthEndpoint should append /health to base', () {
      if (ConfigService.labelApiBase.isNotEmpty) {
        expect(
          ConfigService.healthEndpoint,
          equals('${ConfigService.labelApiBase}/health'),
        );
      }
    });

    test('authHeaders should contain X-API-Key', () {
      final headers = ConfigService.authHeaders;
      expect(headers.containsKey('X-API-Key'), isTrue);
    });

    test('isConfigured requires both base and key', () {
      final isConfigured = ConfigService.labelApiBase.isNotEmpty &&
          ConfigService.labelApiKey.isNotEmpty;
      expect(ConfigService.isConfigured, equals(isConfigured));
    });
  });
}
