import 'package:flutter/widgets.dart';

import '../app/app_scope.dart';

/// 問題回報 #587: where the learner is when they tap 意見回饋 — the page name
/// and, when the page shows one, the word or photo id. Tab navigators report
/// through [FeedbackObserver]; routes name themselves with
/// `RouteSettings(name: …, arguments: id)`, unnamed pushes keep the page
/// below them.
class FeedbackContext {
  static final instance = FeedbackContext();

  static const tabNames = {
    AppTab.camera: '拍照',
    AppTab.album: '相片冊',
    AppTab.review: '複習',
    AppTab.words: '單字本',
    AppTab.settings: '設定',
  };

  /// The tab on screen; null outside the shell (新手引導).
  AppTab? tab;

  /// Set by the review screen when it knows more ("複習 背面").
  String? detail;

  final _stacks = <AppTab?, List<(String, String?)>>{};

  List<(String, String?)> stack(AppTab? tab) => _stacks[tab] ??= [];

  (String, String?) get current {
    final t = tab;
    if (t == null) return ('新手引導', null);
    final root = stack(null);
    if (root.isNotEmpty) return root.last;
    final top = stack(t);
    return top.isNotEmpty ? top.last : (tabNames[t]!, null);
  }

  String get page {
    final name = current.$1;
    final d = detail;
    return d != null && tab == AppTab.review && name == tabNames[tab]
        ? '$name $d'
        : name;
  }

  String? get subject => current.$2;
}

/// Observes one navigator: [tab] for a tab's stack, null for the root one.
class FeedbackObserver extends NavigatorObserver {
  final AppTab? tab;
  final FeedbackContext context;

  FeedbackObserver(this.tab, {FeedbackContext? context})
      : context = context ?? FeedbackContext.instance;

  List<(String, String?)> get _stack => context.stack(tab);

  (String, String?)? _entry(Route<dynamic> route) {
    if (route is! PageRoute) return null;
    final name = route.settings.name;
    final args = route.settings.arguments;
    if (name != null && name != '/') {
      return (name, args is String ? args : null);
    }
    // Unnamed page: keep the one below it (the tab's own name at the bottom).
    return _stack.isNotEmpty
        ? _stack.last
        : tab == null
            ? null
            : (FeedbackContext.tabNames[tab]!, null);
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    final e = _entry(route);
    if (e == null) return;
    _stack.add(e);
    _pageRoutes.add(route);
  }

  final _pageRoutes = <Route<dynamic>>[];

  void _drop(Route<dynamic> route) {
    if (_pageRoutes.remove(route) && _stack.isNotEmpty) _stack.removeLast();
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _drop(route);

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _drop(route);

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    if (oldRoute != null) _drop(oldRoute);
    if (newRoute != null) didPush(newRoute, null);
  }
}
