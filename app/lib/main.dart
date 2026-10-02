import 'dart:async';
import 'services/dictionary_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'app/app_scope.dart';
import 'app/app_shell.dart';
import 'app/phone_frame.dart';
import 'models/vocabulary_profile.dart';
import 'screens/onboarding_screen.dart';
import 'services/app_settings.dart';
import 'services/cefr_lexicon.dart';
import 'services/fsrs_scheduler.dart';
import 'services/lexicon_pack.dart';
import 'services/photo_intake.dart';
import 'services/photo_store.dart';
import 'services/speaker.dart';
import 'services/tagging_queue.dart';
import 'services/word_database_repository.dart';
import 'services/word_database_store.dart';
import 'services/word_detail_service.dart';
import 'services/word_enricher.dart';
import 'theme/mobile_theme.dart';

/// MaterialApp can call its builder with no child during route/bootstrap
/// transitions on Flutter web. Keep the phone shell renderable instead of
/// throwing from a null assertion on a learner's first launch.
Widget phoneFrameBuilder(BuildContext context, Widget? child) =>
    PhoneFrame(child: child ?? const SizedBox.shrink());

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await WordDetailService.instance.load();
  final lexicon = await CefrLexicon.load();
  final settings = await AppSettings.open();

  Future<WordDatabaseRepository> open(String language) async {
    // The downloaded language pack for this direction (assets/lexicon/).
    await LexiconPack.instance
        .load(target: language, native: settings.nativeLanguage);
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

  runApp(PhotoEnglishApp(
    repository: await open(settings.learningLanguage),
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

  void _applyRetention() => _repository.scheduler = FsrsScheduler(
      FsrsParameters(desiredRetention: widget.settings.desiredRetention));

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

  Future<void> _finishOnboarding(OnboardingResult r) async {
    final settings = widget.settings;
    settings.nativeLanguage = r.nativeLanguage;
    await _switchLanguage(r.learningLanguage);
    _repository.setLevel(r.level, source: r.source);
    settings.onboarded = true;
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
      clock: widget.clock,
      child: MaterialApp(
        title: '拍照學單字',
        locale: const Locale('zh', 'TW'),
        supportedLocales: const [Locale('zh', 'TW')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        debugShowCheckedModeBanner: false,
        theme: MobileTheme.light(),
        builder: phoneFrameBuilder,
        home: ListenableBuilder(
          listenable: widget.settings,
          builder: (context, _) => widget.settings.onboarded
              ? AppShell(
                  databaseLibrary: widget.runWorkers,
                  onNavigatorReady: (n) => _navigator.target = n)
              : OnboardingScreen(
                  lexicon: widget.lexicon, onDone: _finishOnboarding),
        ),
      ),
    );
  }
}
