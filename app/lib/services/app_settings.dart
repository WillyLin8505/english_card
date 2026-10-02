import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

/// The languages the MVP supports, as learning or native language (spec
/// section 7: 英文、法文、繁體中文).
const supportedLanguages = {
  'en': '英文（English）',
  'fr': '法文（Français）',
  'zh-TW': '繁體中文'
};

/// The data model already supports multiple languages, but the first
/// published bilingual pack is English → Traditional Chinese only.
const availableLearningLanguages = {'en'};
const availableNativeLanguages = {'zh-TW'};

bool learningLanguageAvailable(String language) =>
    availableLearningLanguages.contains(language);
bool nativeLanguageAvailable(String language) =>
    availableNativeLanguages.contains(language);
String languageOptionLabel(String language, {required bool learning}) {
  final available = learning
      ? learningLanguageAvailable(language)
      : nativeLanguageAvailable(language);
  return '${supportedLanguages[language] ?? language}${available ? '' : ' · 即將推出'}';
}

/// The language's name inside a Chinese sentence ("你對英文熟悉嗎？").
const languageNameZh = {'en': '英文', 'fr': '法文', 'zh-TW': '中文'};

/// Spec section 4's UserLearningSettings, plus where the photo tagger
/// lives (section 2: Ollama + Qwen3-VL-4B on "Predator", 127.0.0.1:8765,
/// X-API-Key) and the language pair. Stored locally like everything
/// else. The learner's level lives in each language's
/// UserVocabularyProfile, not here.
class AppSettings extends ChangeNotifier {
  static const _boxName = 'app_settings';

  final Box<String>? _box;

  String _taggingUrl;
  String _apiKey;
  double _desiredRetention;
  String _learningLanguage;
  String _nativeLanguage;
  bool _onboarded;

  /// Defaults for a build that knows where its tagger is:
  /// `flutter run --dart-define-from-file=tagging.local.json` (see
  /// tagger/README.md). Anything typed in 設定 wins over these.
  static const defaultTaggingUrl = String.fromEnvironment('TAGGING_URL');
  static const defaultApiKey = String.fromEnvironment('TAGGING_API_KEY');

  AppSettings._(this._box)
      : _taggingUrl = _box?.get('taggingUrl') ?? defaultTaggingUrl,
        _apiKey = _box?.get('apiKey') ?? defaultApiKey,
        _desiredRetention =
            double.tryParse(_box?.get('desiredRetention') ?? '') ?? 0.9,
        _learningLanguage =
            learningLanguageAvailable(_box?.get('learningLanguage') ?? 'en')
                ? (_box?.get('learningLanguage') ?? 'en')
                : 'en',
        _nativeLanguage =
            nativeLanguageAvailable(_box?.get('nativeLanguage') ?? 'zh-TW')
                ? (_box?.get('nativeLanguage') ?? 'zh-TW')
                : 'zh-TW',
        _onboarded = _box?.get('onboarded') == 'true';

  /// Settings that live only in memory — for tests and previews.
  AppSettings.inMemory({
    String taggingUrl = '',
    String apiKey = '',
    String learningLanguage = 'en',
    String nativeLanguage = 'zh-TW',
    bool onboarded = true,
  })  : _box = null,
        _taggingUrl = taggingUrl,
        _apiKey = apiKey,
        _desiredRetention = 0.9,
        _learningLanguage = learningLanguage,
        _nativeLanguage = nativeLanguage,
        _onboarded = onboarded;

  static Future<AppSettings> open() async {
    final box = await Hive.openBox<String>(_boxName);
    final settings = AppSettings._(box);
    if (box.get('learningLanguage') != settings.learningLanguage) {
      await box.put('learningLanguage', settings.learningLanguage);
    }
    if (box.get('nativeLanguage') != settings.nativeLanguage) {
      await box.put('nativeLanguage', settings.nativeLanguage);
    }
    return settings;
  }

  /// Tagging endpoint, e.g. `http://127.0.0.1:8765/tag` or a Cloudflare
  /// Web builds use the local app server automatically when no override is set.
  String get taggingUrl => _taggingUrl.trim().isNotEmpty
      ? _taggingUrl
      : kIsWeb
          ? Uri.base.resolve('/tag').toString()
          : '';
  String get apiKey => _taggingUrl.trim().isEmpty && kIsWeb ? '' : _apiKey;
  bool get taggingConfigured => taggingUrl.isNotEmpty;

  /// 期望記憶率 for FSRS.
  double get desiredRetention => _desiredRetention;

  /// The language being learned; each has its own albums, words, cards
  /// and profile (語言資料隔離). Remembered across launches.
  String get learningLanguage => _learningLanguage;

  /// Decides translations, hints and the grade buttons' wording.
  String get nativeLanguage => _nativeLanguage;

  /// Whether the first-run questions (languages, background) are done.
  bool get onboarded => _onboarded;

  /// The level chosen in an older version's settings, used once to start
  /// the learner's profile.
  String? get legacyLevel => _box?.get('level');

  void _save(String key, String value) {
    _box?.put(key, value);
    notifyListeners();
  }

  set taggingUrl(String v) => _save('taggingUrl', _taggingUrl = v.trim());
  set apiKey(String v) => _save('apiKey', _apiKey = v.trim());

  set desiredRetention(double v) =>
      _save('desiredRetention', '${_desiredRetention = v.clamp(0.7, 0.97)}');

  set learningLanguage(String v) {
    assert(supportedLanguages.containsKey(v));
    _save('learningLanguage', _learningLanguage = v);
  }

  set nativeLanguage(String v) {
    assert(supportedLanguages.containsKey(v));
    _save('nativeLanguage', _nativeLanguage = v);
  }

  set onboarded(bool v) => _save('onboarded', '${_onboarded = v}');
}
