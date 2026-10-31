import 'dart:async';
import 'dart:ui' show Locale;

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import '../models/photo.dart';
import '../theme/card_style.dart';
import 'analytics.dart';
import 'cloud_token_store.dart';
import 'crash_reporting.dart';
import 'text_scan.dart';

export '../theme/card_style.dart' show CardStyle;

/// The languages the MVP supports, as learning or native language (spec
/// section 7: 英文、法文、繁體中文).
const supportedLanguages = {
  'en': '英文（English）',
  'fr': '法文（Français）',
  'zh-TW': '繁體中文'
};

/// French as a learning language (問題回報 #496): the owner opened it
/// (問題回報 #700), so it is on by default;
/// `--dart-define=FRENCH_LEARNING=false` builds a version without it.
const frenchLearning =
    bool.fromEnvironment('FRENCH_LEARNING', defaultValue: true);

/// The learning languages this build offers. Not const so tests can close
/// French ([frenchLearning]) without a special build.
final availableLearningLanguages = {'en', if (frenchLearning) 'fr'};
// Interface languages are available independently of published learning packs.
const availableNativeLanguages = {'zh-TW', 'en', 'fr'};

/// Native languages a learning language has a dictionary for (卡 #737,
/// 問題回報 #882): French exists only with English translations so far; the
/// 法→繁中 pack (card #738) opens 'zh-TW' by adding it here. English is
/// learnable from any native language.
final frenchNativeLanguages = {'en'};

/// Whether the [learning]/[native] pair has a dictionary (not just each
/// language on its own).
bool languagePairAvailable(String learning, String native) =>
    learning != 'fr' || frenchNativeLanguages.contains(native);

const frenchNeedsEnglishNative = '法文目前只提供英文母語';

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

/// The supported language closest to the device's, for the first onboarding
/// page before a native language is chosen (問題回報 #496). A device in a
/// language the app doesn't have gets English.
String deviceLanguage(Locale locale) => switch (locale.languageCode) {
      'zh' => 'zh-TW',
      'fr' => 'fr',
      _ => 'en',
    };

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
  String _cloudToken;
  String _cloudEmail;
  double _desiredRetention;
  String _learningLanguage;
  String _nativeLanguage;
  String _englishAccent;
  CardStyle _cardStyle;
  bool _onboarded;
  bool _shareUsageStats;
  int _dailyNewLimit;
  int _dailyReviewLimit;
  bool _showPhotoLabels;

  // 新手引導的「學習目的」與「興趣主題」（卡 #814）: stable keys from
  // interest_topics.dart, comma-joined in the box. Empty = skipped.
  late List<String> _learningGoals = _readList('learningGoals');
  late List<String> _interests = _readList('interests');

  // 各分頁的使用教學（卡 #893）: names of the tabs whose tutorial was
  // seen or skipped, comma-joined in the box.
  late final Set<String> _seenTutorials = _readList('seenTutorials').toSet();

  /// Whether the tutorial of the tab called [tab] (an `AppTab.name`) was
  /// already seen or skipped.
  bool tutorialSeen(String tab) => _seenTutorials.contains(tab);

  void markTutorialSeen(String tab) {
    if (!_seenTutorials.add(tab)) return;
    _save('seenTutorials', _seenTutorials.join(','));
  }

  /// 設定 → 使用教學: shows the tutorial of [tab] again, or of every tab.
  void resetTutorials([String? tab]) {
    if (tab == null) {
      _seenTutorials.clear();
    } else if (!_seenTutorials.remove(tab)) {
      return;
    }
    _save('seenTutorials', _seenTutorials.join(','));
  }

  List<String> _readList(String key) => [
        for (final s in (_box?.get(key) ?? '').split(','))
          if (s.isNotEmpty) s
      ];

  /// Defaults for a build that knows where its tagger is:
  /// `flutter run --dart-define-from-file=tagging.local.json` (see
  /// tagger/README.md). Anything typed in 設定 wins over these.
  static const defaultTaggingUrl = String.fromEnvironment('TAGGING_URL');
  static const defaultApiKey = String.fromEnvironment('TAGGING_API_KEY');

  /// The phone can recognize photos itself (Apple Vision; `LocalVision.probe()`
  /// at start-up). Owner decision 2026-10-18 (問題回報 #265): the published
  /// app recognizes on the device and ships its dictionary; a tagging server
  /// is a developer option, so the store build has no address or key to set.
  static bool localRecognition = false;

  /// Builds that may talk to a tagging server show its address and key in
  /// 設定: the web page (its own server), a build with TAGGING_URL, or
  /// `--dart-define=DEV_TOOLS=true`.
  static const developerTools =
      bool.fromEnvironment('DEV_TOOLS') || defaultTaggingUrl != '';

  /// Set when start-up found a stored pair without a dictionary (繁中母語＋
  /// 法文) and went back to English; the app shows it once ([takePairReset]).
  bool _pairReset = false;

  bool takePairReset() {
    final v = _pairReset;
    _pairReset = false;
    return v;
  }

  AppSettings._(this._box)
      : _taggingUrl = _box?.get('taggingUrl') ?? defaultTaggingUrl,
        _apiKey = _box?.get('apiKey') ?? defaultApiKey,
        _cloudToken = '',
        _cloudEmail = _box?.get('cloudEmail') ?? '',
        _desiredRetention =
            (double.tryParse(_box?.get('desiredRetention') ?? '') ?? 0.9)
                .clamp(minRetention, maxRetention),
        _learningLanguage =
            learningLanguageAvailable(_box?.get('learningLanguage') ?? 'en')
                ? (_box?.get('learningLanguage') ?? 'en')
                : 'en',
        _nativeLanguage =
            nativeLanguageAvailable(_box?.get('nativeLanguage') ?? 'zh-TW')
                ? (_box?.get('nativeLanguage') ?? 'zh-TW')
                : 'zh-TW',
        _englishAccent =
            _box?.get('englishAccent') == 'en-US' ? 'en-US' : 'en-GB',
        _cardStyle = CardStyle.parse(_box?.get('cardStyle')),
        _onboarded = _box?.get('onboarded') == 'true',
        // Absent means off: existing installs stop sending until they opt in.
        _shareUsageStats = _box?.get('shareUsageStats') == 'true',
        // Absent means on (問題回報 #406); a learner who switched it off keeps that.
        _showPhotoLabels = _box?.get('showPhotoLabels') != 'false',
        _reviewScope = _box?.get('reviewScope') ?? 'all',
        _dailyNewLimit = (int.tryParse(_box?.get('dailyNewLimit') ?? '') ??
                defaultDailyNewLimit)
            .clamp(minDailyNew, maxDailyNew),
        _dailyReviewLimit =
            (int.tryParse(_box?.get('dailyReviewLimit') ?? '') ??
                    defaultDailyReviewLimit)
                .clamp(minDailyReview, maxDailyReview);

  /// Settings that live only in memory — for tests and previews.
  AppSettings.inMemory({
    String taggingUrl = '',
    String apiKey = '',
    String learningLanguage = 'en',
    String nativeLanguage = 'zh-TW',
    String englishAccent = 'en-GB',
    CardStyle cardStyle = CardStyle.fallback,
    bool onboarded = true,
    bool shareUsageStats = false,
    bool showPhotoLabels = true,
    // Tests start with every tab tutorial seen, so the card does not cover
    // the screen under test (卡 #893).
    bool tutorialsSeen = true,
  })  : _box = null,
        _taggingUrl = taggingUrl,
        _apiKey = apiKey,
        _cloudToken = '',
        _cloudEmail = '',
        _desiredRetention = 0.9,
        _learningLanguage = learningLanguage,
        _nativeLanguage = nativeLanguage,
        _englishAccent = englishAccent,
        _cardStyle = cardStyle,
        _onboarded = onboarded,
        _shareUsageStats = shareUsageStats,
        _showPhotoLabels = showPhotoLabels,
        _reviewScope = 'all',
        _dailyNewLimit = defaultDailyNewLimit,
        _dailyReviewLimit = defaultDailyReviewLimit {
    if (tutorialsSeen) {
      _seenTutorials.addAll(['camera', 'album', 'review', 'words', 'settings']);
    }
  }

  CloudTokenStore? _tokenStore;

  @visibleForTesting
  void attachTokenStoreForTest(CloudTokenStore store) => _tokenStore = store;

  /// Card #910: the login token is kept in the Keychain (not the Hive box); an
  /// older build's token in the box is moved there once.
  Future<void> _loadCloudToken(CloudTokenStore store) async {
    _tokenStore = store;
    try {
      var token = await store.read();
      final legacy = _box?.get('cloudToken') ?? '';
      if (token.isEmpty && legacy.isNotEmpty) {
        await store.write(token = legacy);
      }
      if (legacy.isNotEmpty) await _box?.delete('cloudToken');
      _cloudToken = token;
    } catch (_) {
      // No Keychain (web, tests): stay signed out rather than store it in the box.
    }
  }

  static Future<AppSettings> open({CloudTokenStore? tokenStore}) async {
    final box = await Hive.openBox<String>(_boxName);
    final settings = AppSettings._(box);
    await settings._loadCloudToken(tokenStore ?? const KeychainTokenStore());
    if (!languagePairAvailable(
        settings.learningLanguage, settings.nativeLanguage)) {
      settings._learningLanguage = 'en';
      settings._pairReset = true;
    }
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

  /// No server address and the device can classify: photos are recognized
  /// on the phone and never uploaded.
  bool get usesLocalRecognition =>
      !kIsWeb && _taggingUrl.trim().isEmpty && localRecognition;

  /// Whether 設定 offers the server address / key fields at all.
  bool get showsTaggingServer =>
      kIsWeb || developerTools || _taggingUrl.trim().isNotEmpty;

  /// Something can recognize photos: the device itself or a server.
  bool get taggingConfigured => usesLocalRecognition || taggingUrl.isNotEmpty;

  /// The range 設定's slider offers; a stored or restored value outside it
  /// would break the slider (card #228), so it is clamped to the same range.
  static const minRetention = 0.8, maxRetention = 0.95;

  /// 期望記憶率 for FSRS.
  double get desiredRetention => _desiredRetention;

  /// 每日上限 (問題回報 #398): at most this many first-time cards and due
  /// reviews are scheduled per day; the rest wait for tomorrow.
  static const defaultDailyNewLimit = 20, minDailyNew = 5, maxDailyNew = 100;
  static const defaultDailyReviewLimit = 100,
      minDailyReview = 20,
      maxDailyReview = 500;

  /// 複習範圍 (問題回報 #412), remembered between runs: `all`, `new`
  /// (今天新加的), `weak` (弱項單字) or `album:<id>` (相片冊／卡片集).
  String _reviewScope;
  String get reviewScope => _reviewScope;
  set reviewScope(String v) => _save('reviewScope', _reviewScope = v);

  int get dailyNewLimit => _dailyNewLimit;
  int get dailyReviewLimit => _dailyReviewLimit;

  set dailyNewLimit(int v) => _save(
      'dailyNewLimit', '${_dailyNewLimit = v.clamp(minDailyNew, maxDailyNew)}');
  set dailyReviewLimit(int v) => _save('dailyReviewLimit',
      '${_dailyReviewLimit = v.clamp(minDailyReview, maxDailyReview)}');

  /// The language being learned; each has its own albums, words, cards
  /// and profile (語言資料隔離). Remembered across launches.
  String get learningLanguage => _learningLanguage;

  /// Decides translations, hints and the grade buttons' wording.
  String get nativeLanguage => _nativeLanguage;

  /// Which English accent 發音 and TTS use: "en-GB" (default, spec section
  /// 7) or "en-US".
  String get englishAccent => _englishAccent;

  /// 卡片樣式 of the review card (問題回報 #317); [CardStyle.immersive] (B) by
  /// default.
  CardStyle get cardStyle => _cardStyle;

  /// Whether the first-run questions (languages, background) are done.
  bool get onboarded => _onboarded;

  /// 設定 → 分享使用統計. Default off; PostHog sends nothing until this is on.
  bool get shareUsageStats => _shareUsageStats;

  /// 設定 → 照片上的單字標示: the word's label on the photo of a review card.
  /// Default on.
  bool get showPhotoLabels => _showPhotoLabels;

  /// Why the learner learns (travel, work…), keys of [learningGoalOptions].
  List<String> get learningGoals => List.unmodifiable(_learningGoals);

  /// Topics the learner likes, keys of [interestOptions]; 卡片集 lists the
  /// matching decks first.
  List<String> get interests => List.unmodifiable(_interests);

  set learningGoals(List<String> v) {
    _learningGoals = [...v];
    _save('learningGoals', _learningGoals.join(','));
  }

  set interests(List<String> v) {
    _interests = [...v];
    _save('interests', _interests.join(','));
  }

  /// The level chosen in an older version's settings, used once to start
  /// the learner's profile.
  String? get legacyLevel => _box?.get('level');

  void _save(String key, String value) {
    _box?.put(key, value);
    notifyListeners();
  }

  set taggingUrl(String v) => _save('taggingUrl', _taggingUrl = v.trim());
  set apiKey(String v) => _save('apiKey', _apiKey = v.trim());

  /// 雲端備份帳號 (card #902): the login token and email of the account the
  /// backup is stored under. Not part of a backup file (belongs to this device).
  String get cloudToken => _cloudToken;
  String get cloudEmail => _cloudEmail;
  bool get cloudSignedIn => _cloudToken.isNotEmpty;

  /// 跨裝置自動同步 (card #912). These belong to this device: not in a
  /// backup and not synced. Photos wait for Wi-Fi unless the learner says.
  bool get cloudSyncEnabled => _flag('cloudSyncEnabled', true);
  set cloudSyncEnabled(bool v) => _setFlag('cloudSyncEnabled', v);
  bool get syncPhotos => _flag('syncPhotos', true);
  set syncPhotos(bool v) => _setFlag('syncPhotos', v);
  bool get syncPhotosWifiOnly => _flag('syncPhotosWifiOnly', true);
  set syncPhotosWifiOnly(bool v) => _setFlag('syncPhotosWifiOnly', v);

  final _flags = <String, bool>{};
  bool _flag(String key, bool byDefault) =>
      _flags[key] ??
      switch (_box?.get(key)) {
        'true' => true,
        'false' => false,
        _ => byDefault,
      };
  void _setFlag(String key, bool v) {
    _flags[key] = v;
    _save(key, '$v');
  }

  void setCloudAccount(String token, String email) {
    _cloudToken = token;
    final store = _tokenStore;
    if (store != null) {
      (token.isEmpty ? store.delete() : store.write(token)).catchError((_) {});
    }
    _save('cloudEmail', _cloudEmail = email);
  }

  /// Usage counters for the account's stats report (card #911). Numbers only; kept
  /// out of backups and without notifyListeners so a tap never rebuilds the app.
  final _usage = <String, String>{}; // used when there is no Hive box (tests)
  String? _usageGet(String k) => _box?.get(k) ?? _usage[k];
  void _usagePut(String k, String v) {
    _usage[k] = v;
    _box?.put(k, v);
  }

  int usageCount(String key) => int.tryParse(_usageGet('usage_$key') ?? '') ?? 0;
  void bumpUsage(String key) => _usagePut('usage_$key', '${usageCount(key) + 1}');

  /// Raw usage-store access for the anonymous events (card #914).
  String? usageValue(String key) => _usageGet(key);
  void setUsageValue(String key, String v) => _usagePut(key, v);

  /// 設定 → 匿名使用事件 (card #914). Default on; off means nothing is queued or sent.
  bool get anonymousEvents => _usageGet('anonEvents') != 'false';
  set anonymousEvents(bool v) {
    _usagePut('anonEvents', '$v');
    notifyListeners();
  }

  /// When the last stats report reached the server (ms since epoch; 0 = never).
  int get statsSentAt => int.tryParse(_usageGet('statsSentAt') ?? '') ?? 0;
  set statsSentAt(int v) => _usagePut('statsSentAt', '$v');

  set desiredRetention(double v) => _save('desiredRetention',
      '${_desiredRetention = v.clamp(minRetention, maxRetention)}');

  set learningLanguage(String v) {
    assert(supportedLanguages.containsKey(v));
    _save('learningLanguage', _learningLanguage = v);
    _flush();
  }

  set nativeLanguage(String v) {
    assert(supportedLanguages.containsKey(v));
    _save('nativeLanguage', _nativeLanguage = v);
    _flush();
  }

  /// The languages pick which data opens at launch: written to disk at once,
  /// so an app closed right after the switch does not come back in the
  /// other language (owner's iPhone 10/27: 切回英文 was lost, the app
  /// reopened in an empty French).
  void _flush() {
    try {
      unawaited(_box?.flush());
    } catch (_) {}
  }

  set englishAccent(String v) {
    assert(v == 'en-GB' || v == 'en-US');
    _save('englishAccent', _englishAccent = v);
  }

  set cardStyle(CardStyle v) => _save('cardStyle', (_cardStyle = v).name);

  PhotoScanMode? _scanMode;

  /// 找物品／找文字／兩者都找 for the next photo (問題回報 #324): the last
  /// choice, else things in the picture — or text on a device that can
  /// read text but has no picture recognizer. Text is never offered where
  /// the device can't read it (the web build).
  PhotoScanMode get scanMode {
    final saved =
        _scanMode ?? PhotoScanMode.values.asNameMap()[_box?.get('scanMode')];
    if (saved != null && (!saved.findsText || TextScan.available)) {
      return saved;
    }
    return !taggingConfigured && TextScan.available
        ? PhotoScanMode.text
        : PhotoScanMode.objects;
  }

  set scanMode(PhotoScanMode v) => _save('scanMode', (_scanMode = v).name);

  set showPhotoLabels(bool v) =>
      _save('showPhotoLabels', '${_showPhotoLabels = v}');

  set onboarded(bool v) => _save('onboarded', '${_onboarded = v}');

  set shareUsageStats(bool v) {
    _shareUsageStats = v;
    _save('shareUsageStats', '$v');
    Analytics.instance.sharing = v;
    CrashReporting.instance.sharing = v;
  }
}
