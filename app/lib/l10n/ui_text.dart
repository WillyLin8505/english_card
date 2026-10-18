import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import 'ui_catalog.dart';

/// UI copy only. Dictionary text, learner input and review hints use their
/// existing content pipeline and must not be passed through this catalog.
String ui(BuildContext context, String source) {
  final preview = context.dependOnInheritedWidgetOfExactType<UiLanguageScope>();
  final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
  return translateUi(
      source, preview?.language ?? scope?.settings.nativeLanguage ?? 'zh-TW');
}

/// First-run language preview, without persisting an unfinished onboarding.
class UiLanguageScope extends InheritedWidget {
  final String language;
  const UiLanguageScope(
      {super.key, required this.language, required super.child});
  @override
  bool updateShouldNotify(UiLanguageScope oldWidget) =>
      language != oldWidget.language;
}

/// A reactive UI label, including labels inside retained tabs and open dialogs.
/// Keeping the source copy here also lets const widgets react to settings.
class UiText extends StatelessWidget {
  final String data;
  final TextStyle? style;
  final TextAlign? textAlign;
  final int? maxLines;
  final TextOverflow? overflow;
  final bool? softWrap;
  final TextWidthBasis? textWidthBasis;
  const UiText(this.data,
      {super.key,
      this.style,
      this.textAlign,
      this.maxLines,
      this.overflow,
      this.softWrap,
      this.textWidthBasis});

  @override
  Widget build(BuildContext context) {
    return Text(ui(context, data),
        style: style,
        textAlign: textAlign,
        maxLines: maxLines,
        overflow: overflow,
        softWrap: softWrap,
        textWidthBasis: textWidthBasis);
  }
}
