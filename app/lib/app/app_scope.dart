import 'package:flutter/widgets.dart';

import '../services/app_settings.dart';
import '../services/cefr_lexicon.dart';
import '../services/photo_intake.dart';
import '../services/photo_store.dart';
import '../services/speaker.dart';
import '../services/tagging_queue.dart';
import '../services/word_database_repository.dart';
import '../services/word_enricher.dart';

/// The bottom tabs: the Figma bar (拍照 / 相片冊 / 單字本 / 設定) plus the
/// Flashcard entry spec section 7 adds (底部導覽增加 Flashcard 入口；五個
/// 導覽按鈕的排列暫未決定 — here it sits in the middle).
enum AppTab { camera, album, review, words, settings }

/// Cross-tab navigation the shell provides to screens — e.g. a captured
/// photo opens in the 相片冊 tab, as the mock's photo-detail tab bar shows.
abstract interface class AppNavigator {
  void selectTab(AppTab tab);

  /// Opens 照片詳情 for [photoId] in the 相片冊 tab.
  void openPhoto(String photoId);

  /// Opens 項目照片 (every photo containing the word) in the 相片冊 tab.
  void openWordPhotos(String wordEntryId);

  /// Opens 單字詳情 full-screen (no tab bar, as in the mock).
  void openWord(String wordEntryId, {String? occurrenceId});

  /// A review run is going on: the tab bar hides so a stray tap can't
  /// switch tabs mid-card (owner decision 問題回報 #101).
  void setReviewing(bool reviewing);
}

/// Forwards to the shell once it exists — [AppScope] sits above the shell,
/// so it can't hold the shell itself.
class AppNavigatorProxy implements AppNavigator {
  AppNavigator? target;

  AppNavigator get _t => target ?? (throw StateError('AppShell not built yet'));

  @override
  void selectTab(AppTab tab) => _t.selectTab(tab);

  @override
  void openPhoto(String photoId) => _t.openPhoto(photoId);

  @override
  void openWordPhotos(String wordEntryId) => _t.openWordPhotos(wordEntryId);

  @override
  void openWord(String wordEntryId, {String? occurrenceId}) =>
      _t.openWord(wordEntryId, occurrenceId: occurrenceId);

  @override
  void setReviewing(bool reviewing) => target?.setReviewing(reviewing);
}

/// Which tab is showing, for screens that must pause when hidden (the
/// camera) or save when left (照片詳情). Tab screens live in an
/// IndexedStack, so they stay built.
class ActiveTabScope extends InheritedWidget {
  final AppTab tab;

  const ActiveTabScope({super.key, required this.tab, required super.child});

  static AppTab? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ActiveTabScope>()?.tab;

  @override
  bool updateShouldNotify(ActiveTabScope old) => tab != old.tab;
}

/// App-wide services, provided above the shell. [repository] is the
/// current learning language's word database; switching language swaps
/// it (and everything below rebuilds).
class AppScope extends InheritedWidget {
  final WordDatabaseRepository repository;
  final AppSettings settings;
  final PhotoStore photoStore;
  final PhotoIntake intake;
  final TaggingQueue queue;
  final WordEnricher enricher;
  final Speaker speaker;
  final CefrLexicon lexicon;
  final AppNavigator navigator;

  /// Opens another learning language's data (設定 → 學習語言).
  final Future<void> Function(String language) switchLanguage;

  /// Injectable for tests so 下次出現 labels are deterministic.
  final DateTime Function() clock;

  const AppScope({
    super.key,
    required this.repository,
    required this.settings,
    required this.photoStore,
    required this.intake,
    required this.queue,
    required this.enricher,
    required this.speaker,
    required this.lexicon,
    required this.navigator,
    required this.switchLanguage,
    this.clock = DateTime.now,
    required super.child,
  });

  static AppScope of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!;

  @override
  bool updateShouldNotify(AppScope old) =>
      repository != old.repository ||
      settings != old.settings ||
      photoStore != old.photoStore ||
      navigator != old.navigator;
}
