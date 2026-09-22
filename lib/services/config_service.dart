class ConfigService {
  static const String _labelApiBase =
      String.fromEnvironment('LABEL_API_BASE', defaultValue: '');
  static const String _labelApiKey =
      String.fromEnvironment('LABEL_API_KEY', defaultValue: '');
  static const bool _mockLabel =
      bool.fromEnvironment('MOCK_LABEL', defaultValue: true);

  static String get labelApiBase => _labelApiBase;
  static String get labelApiKey => _labelApiKey;
  static bool get mockLabel => _mockLabel;

  static bool get isConfigured =>
      _labelApiBase.isNotEmpty && _labelApiKey.isNotEmpty;

  static bool get shouldUseMock => _mockLabel || !isConfigured;

  static String get labelEndpoint => '$_labelApiBase/v1/label';
  static String get healthEndpoint => '$_labelApiBase/health';

  static Map<String, String> get authHeaders => {
        'X-API-Key': _labelApiKey,
      };

  static String get configSummary {
    if (shouldUseMock) {
      return 'Mock 模式';
    }
    final host = Uri.tryParse(_labelApiBase)?.host ?? _labelApiBase;
    return '連線至 $host';
  }
}
