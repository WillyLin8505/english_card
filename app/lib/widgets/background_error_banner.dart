import '../l10n/ui_text.dart';
import 'package:flutter/material.dart';

import '../services/background_errors.dart';
import 'mobile/common.dart' show Tap;

/// A dismissible strip above whichever screen is open, showing the latest
/// [BackgroundErrors] message with a 重試 action when one was given
/// (問題回報 #175: dictionary sync and other background failures used to
/// only reach the debug log). Lives above the navigator, like
/// [TaggingProgress], so changing pages does not hide it.
class BackgroundErrorBanner extends StatelessWidget {
  final BackgroundErrors errors;
  final Widget child;

  const BackgroundErrorBanner(
      {super.key, required this.errors, required this.child});

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: errors,
        builder: (context, _) => Column(
          children: [
            if (errors.message != null)
              Material(
                color: Theme.of(context).colorScheme.errorContainer,
                child: SafeArea(
                  bottom: false,
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    child: Row(
                      children: [
                        Expanded(child: UiText(errors.message!)),
                        if (errors.retry != null)
                          TextButton(
                            onPressed: () {
                              final retry = errors.retry!;
                              errors.dismiss();
                              retry();
                            },
                            child: const UiText('重試'),
                          ),
                        // Plain Icon + Tap, not IconButton: this banner sits
                        // above the Navigator, so a Tooltip here would find
                        // no Overlay to show in.
                        Tap(
                          label: ui(context, '關閉'),
                          onTap: errors.dismiss,
                          child: const Padding(
                            padding: EdgeInsets.all(12),
                            child: Icon(Icons.close, size: 18),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            Expanded(child: child),
          ],
        ),
      );
}
