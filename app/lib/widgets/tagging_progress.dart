import '../l10n/ui_text.dart';
import 'package:flutter/material.dart';

import '../services/tagging_queue.dart';

/// Lives above the navigator so changing pages does not hide queue progress.
class TaggingProgress extends StatelessWidget {
  final TaggingQueue queue;
  final Widget child;

  const TaggingProgress({super.key, required this.queue, required this.child});

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: queue,
        builder: (context, _) => Column(
          children: [
            Expanded(child: child),
            if (queue.hasWork)
              Material(
                color: Theme.of(context).colorScheme.surfaceContainer,
                child: SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        LinearProgressIndicator(
                          value: queue.total == 0
                              ? null
                              : queue.completed / queue.total,
                        ),
                        const SizedBox(height: 6),
                        UiText('AI 打標籤：${queue.progressLabel}'),
                        if (queue.failed > 0)
                          UiText('${queue.failed} 張辨識失敗，可在相片頁重試'),
                        const UiText('可離開此頁，會繼續處理；請保持 App 開啟。',
                            style: TextStyle(fontSize: 12)),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
}
