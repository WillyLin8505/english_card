import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import '../screens/album_screen.dart';
import '../screens/database_library_screen.dart';
import '../screens/camera_screen.dart';
import '../screens/flashcard_screen.dart';
import '../screens/photo_detail_screen.dart';
import '../screens/photo_grid_screen.dart';
import '../screens/settings_screen.dart';
import '../screens/word_database_screen.dart';
import '../screens/word_detail_screen.dart';
import '../widgets/mobile/tab_bar.dart';
import 'app_scope.dart';
import '../theme/mobile_theme.dart';

/// The five tabs, each with its own navigation stack so the tab bar
/// stays visible on pushed screens, as the mocks show (照片詳情 and
/// 項目照片 keep the bar; 單字詳情 is full screen, on the root navigator).
///
/// Created by [AppScope]'s owner; screens reach it through
/// `AppScope.of(context).navigator`.
class AppShell extends StatefulWidget {
  final AppTab initialTab;
  final bool databaseLibrary;
  final ValueChanged<AppNavigator> onNavigatorReady;

  const AppShell(
      {super.key,
      this.initialTab = AppTab.camera,
      this.databaseLibrary = false,
      required this.onNavigatorReady});

  @override
  State<AppShell> createState() => AppShellState();
}

class AppShellState extends State<AppShell> implements AppNavigator {
  late AppTab _tab = widget.initialTab;
  bool _reviewing = false;
  final _navigators = {
    for (final t in AppTab.values) t: GlobalKey<NavigatorState>()
  };

  @override
  void initState() {
    super.initState();
    widget.onNavigatorReady(this);
  }

  NavigatorState? _nav(AppTab tab) => _navigators[tab]!.currentState;

  @override
  void selectTab(AppTab tab) {
    if (tab == _tab) {
      // Re-tapping the current tab goes back to its first screen.
      _nav(tab)?.popUntil((r) => r.isFirst);
      return;
    }
    setState(() => _tab = tab);
  }

  void _pushInAlbumTab(Widget screen) {
    setState(() => _tab = AppTab.album);
    // The album navigator may not have built yet if the tab was never
    // shown; push after this frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _nav(AppTab.album)?.push(MaterialPageRoute<void>(builder: (_) => screen));
    });
  }

  @override
  void openPhoto(String photoId) =>
      _pushInAlbumTab(PhotoDetailScreen(photoId: photoId));

  @override
  void openWordPhotos(String wordEntryId) =>
      _pushInAlbumTab(PhotoGridScreen.word(wordEntryId: wordEntryId));

  @override
  void setReviewing(bool reviewing) {
    if (reviewing == _reviewing || !mounted) return;
    // Called from the review screen, possibly while it is being built
    // (a language switch ends the run): apply after this frame then.
    if (SchedulerBinding.instance.schedulerPhase ==
        SchedulerPhase.persistentCallbacks) {
      WidgetsBinding.instance.addPostFrameCallback((_) => setReviewing(reviewing));
      return;
    }
    setState(() => _reviewing = reviewing);
  }

  @override
  void openWord(String wordEntryId, {String? occurrenceId}) {
    Navigator.of(context, rootNavigator: true).push(MaterialPageRoute<void>(
      builder: (_) => WordDetailScreen(
          wordEntryId: wordEntryId, occurrenceId: occurrenceId),
    ));
  }

  Widget _root(AppTab tab) => switch (tab) {
        AppTab.camera => const CameraScreen(),
        AppTab.album => widget.databaseLibrary
            ? const DatabaseLibraryScreen(photos: true)
            : const AlbumScreen(),
        AppTab.review => const FlashcardScreen(),
        AppTab.words => widget.databaseLibrary
            ? const DatabaseLibraryScreen(photos: false)
            : const WordDatabaseScreen(),
        AppTab.settings => const SettingsScreen(),
      };

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        final nav = _nav(_tab);
        if (nav != null && nav.canPop()) {
          nav.pop();
        } else if (_tab != AppTab.camera) {
          setState(() => _tab = AppTab.camera);
        } else {
          SystemNavigator.pop();
        }
      },
      child: Scaffold(
        backgroundColor: MColors.canvas,
        body: ActiveTabScope(
          tab: _tab,
          child: IndexedStack(
            index: _tab.index,
            children: [
              for (final tab in AppTab.values)
                Navigator(
                  key: _navigators[tab],
                  onGenerateRoute: (_) =>
                      MaterialPageRoute<void>(builder: (_) => _root(tab)),
                ),
            ],
          ),
        ),
        bottomNavigationBar: _reviewing && _tab == AppTab.review
            ? null
            : MobileTabBar(current: _tab, onSelect: selectTab),
      ),
    );
  }
}
