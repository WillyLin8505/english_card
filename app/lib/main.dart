import 'dart:async';
import 'l10n/ui_text.dart';
import 'services/dictionary_sync.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'app/app_scope.dart';
import 'app/app_shell.dart';
import 'app/phone_frame.dart';
import 'models/vocabulary_profile.dart';
import 'screens/onboarding_screen.dart';
import 'services/app_settings.dart';
import 'services/background_errors.dart';
import 'services/cefr_lexicon.dart';
import 'services/lexicon_pack.dart';
import 'services/photo_intake.dart';
import 'services/photo_store.dart';
import 'services/speaker.dart';
import 'services/tagging_queue.dart';
import 'services/web_fonts.dart';
import 'services/word_database_repository.dart';
import 'services/word_database_store.dart';
import 'services/word_detail_service.dart';
import 'services/local_vision.dart';
import 'services/text_scan.dart';
import 'services/word_enricher.dart';
import 'theme/mobile_theme.dart';
import 'widgets/background_error_banner.dart';
import 'widgets/tagging_progress.dart';
import 'services/analytics.dart';

/// MaterialApp can call its builder with no child during route/bootstrap
/// transitions on Flutter web. Keep the phone shell renderable instead of
/// throwing from a null assertion on a learner's first launch.
Widget phoneFrameBuilder(BuildContext context, Widget? child) =>
    PhoneFrame(child: child ?? const SizedBox.shrink());

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Web only: the Chinese font loads in the background, never blocking the
  // first frame (問題回報 #357); text re-lays out when it arrives.
  unawaited(loadWebCjkFont());
  await Hive.initFlutter();
  await WordDetailService.instance.load();
  final lexicon = await CefrLexicon.load();
  final settings = await AppSettings.open();
  // Photos are recognized on the phone when it can (Apple Vision); only a
  // developer build with a server address uploads them (問題回報 #265).
  AppSettings.localRecognition = await LocalVision.probe();
  TextScan.available = await TextScan.probe();
  // Usage analytics (PostHog). Nothing is sent until 分享使用統計 is on,
  // and nothing is sent without POSTHOG_API_KEY.
  Analytics.instance.sharing = settings.shareUsageStats;
  await Analytics.instance.start();

  Future<WordDatabaseRepository> open(String language) async {
    // The downloaded language pack for this direction (assets/lexicon/).
    // The web page doesn't wait for it (30 MB, 問題回報 #357): DictionarySync
    // fills it from the cached or online dictionary once the app is up.
    if (!kIsWeb) {
      await LexiconPack.instance
          .load(target: language, native: settings.nativeLanguage);
    }
    final store = await HiveWordDatabaseStore.open(language: language);
    // Database content is shown by the live catalog. Personal collections
    // start empty; existing saved photos and review records stay intact.
    if (store.needsSeed) {
      await store.seed(const WordDatabaseData());
    }
    return WordDatabaseRepository.fromData(
      store.load(),
      language: language,
      store: store,
      // The downloaded language pack first, then the older bundled data.
      lookupDetail: (w) =>
          LexiconPack.instance.detail(w) ??
          WordDetailService.instance.lookup(w),
      profile: UserVocabularyProfile.start(settings.legacyLevel ?? 'A1'),
    )..linkLexicon(LexiconPack.instance);
  }

  final repository = await open(settings.learningLanguage);
  runApp(PhotoEnglishApp(
    repository: repository,
    settings: settings,
    photoStore: await PhotoStore.open(),
    lexicon: lexicon,
    openRepository: open,
  ));
}

class PhotoEnglishApp extends StatefulWidget {
  final WordDatabaseRepository repository;
  final AppSettings settings;
  final PhotoStore photoStore;
  final CefrLexicon lexicon;

  /// Opens the word database of another learning language.
  final Future<WordDatabaseRepository> Function(String language)?
      openRepository;
  final Speaker? speaker;

  /// Background workers (tagging queue, word data); off in widget tests.
  final bool runWorkers;
  final DateTime Function() clock;

  const PhotoEnglishApp({
    super.key,
    required this.repository,
    required this.settings,
    required this.photoStore,
    required this.lexicon,
    this.openRepository,
    this.speaker,
    this.runWorkers = true,
    this.clock = DateTime.now,
  });

  @override
  State<PhotoEnglishApp> createState() => _PhotoEnglishAppState();
}

class _PhotoEnglishAppState extends State<PhotoEnglishApp> {
  final _navigator = AppNavigatorProxy();
  late WordDatabaseRepository _repository = widget.repository;
  late final _intake =
      PhotoIntake(repository: () => _repository, photoStore: widget.photoStore);
  late final _queue = TaggingQueue(
    repository: () => _repository,
    settings: widget.settings,
    intake: _intake,
    lexicon: () => widget.lexicon,
  );
  late final _enricher = WordEnricher(
    repository: () => _repository,
    settings: widget.settings,
    intake: _intake,
    lexicon: () => widget.lexicon,
    queue: _queue,
  );
  late final Speaker _speaker = widget.speaker ?? DeviceSpeaker();

  @override
  void initState() {
    super.initState();
    _applyRetention();
    widget.settings.addListener(_applyRetention);
    if (widget.runWorkers) {
      _queue.start();
      unawaited(
          DictionarySync.instance.start(widget.settings, () => _repository));
      _enricher.start();
    }
  }

  @override
  void dispose() {
    widget.settings.removeListener(_applyRetention);
    _queue.dispose();
    _enricher.dispose();
    super.dispose();
  }

  void _applyRetention() =>
      _repository.setDesiredRetention(widget.settings.desiredRetention);

  Future<void> _switchLanguage(String language) async {
    final open = widget.openRepository;
    if (open == null || language == _repository.language) return;
    final next = await open(language);
    widget.settings.learningLanguage = language;
    setState(() => _repository = next);
    _applyRetention();
    unawaited(DictionarySync.instance.refresh());
    _queue.process();
    _enricher.process();
  }

  /// After 從備份還原: the store holds new data (and maybe another
  /// learning language), so open it again.
  Future<void> _reloadData() async {
    final open = widget.openRepository;
    if (open == null) return;
    final next = await open(widget.settings.learningLanguage);
    setState(() => _repository = next);
    _applyRetention();
    _queue.process();
    _enricher.process();
  }

  Future<void> _finishOnboarding(OnboardingResult r) async {
    final settings = widget.settings;
    settings.nativeLanguage = r.nativeLanguage;
    await _switchLanguage(r.learningLanguage);
    _repository.setLevel(r.level, source: r.source);
    settings.onboarded = true;
    Analytics.instance.capture('onboarding_completed', {
      'learning_language': r.learningLanguage,
      'native_language': r.nativeLanguage,
      'level': r.level.toString(),
      'level_source': r.source.toString(),
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      repository: _repository,
      settings: widget.settings,
      photoStore: widget.photoStore,
      intake: _intake,
      queue: _queue,
      enricher: _enricher,
      speaker: _speaker,
      lexicon: widget.lexicon,
      navigator: _navigator,
      switchLanguage: _switchLanguage,
      reloadData: _reloadData,
      clock: widget.clock,
      child: ListenableBuilder(
        listenable: widget.settings,
        builder: (context, _) => MaterialApp(
          title: ui(context, '拍照學單字'),
          locale: widget.settings.nativeLanguage == 'zh-TW'
              ? const Locale('zh', 'TW')
              : Locale(widget.settings.nativeLanguage),
          supportedLocales: const [
            Locale('zh', 'TW'),
            Locale('en'),
            Locale('fr')
          ],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          debugShowCheckedModeBanner: false,
          theme: MobileTheme.light(),
          builder: (context, child) => phoneFrameBuilder(
              context,
              BackgroundErrorBanner(
                errors: BackgroundErrors.instance,
                child: TaggingProgress(
                    queue: _queue, child: child ?? const SizedBox.shrink()),
              )),
          home: ListenableBuilder(
            listenable: widget.settings,
            builder: (context, _) => widget.settings.onboarded
                ? AppShell(onNavigatorReady: (n) => _navigator.target = n)
                : OnboardingScreen(
                    lexicon: widget.lexicon,
                    onDone: _finishOnboarding,
                    uiLanguage: deviceLanguage(
                        WidgetsBinding.instance.platformDispatcher.locale)),
          ),
        ),
      ),
    );
  }
}
