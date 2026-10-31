import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';

/// 學習進度 (問題回報 #1172, owner: 連續天數和進度頁都做): the streak, the
/// last 30 days of reviews and the totals, all derived from the local
/// ReviewLog by [LearningInsights].
class ProgressScreen extends StatelessWidget {
  const ProgressScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ins = AppScope.of(context).repository.insights();
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            MNavBar(
              title: '學習進度',
              leading: BackNavButton(onTap: () => Navigator.of(context).pop()),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(MSpace.lg),
                children: [
                  Row(
                    children: [
                      _stat('streak-current', '${ins.currentStreak}', '連續天數'),
                      const SizedBox(width: 12),
                      _stat('streak-longest', '${ins.longestStreak}', '最長連續'),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _stat('total-days', '${ins.activeDays}', '學習天數'),
                      const SizedBox(width: 12),
                      _stat('total-reviews', '${ins.total}', '複習次數'),
                    ],
                  ),
                  const SizedBox(height: 24),
                  UiText('最近 30 天',
                      style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                  const SizedBox(height: 12),
                  _Bars(values: ins.monthly),
                  const SizedBox(height: 8),
                  UiText(
                      ins.total == 0
                          ? '複習幾次之後，這裡會顯示你的學習進度。'
                          : '每一根代表一天的複習次數，最右邊是今天。',
                      style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stat(String key, String value, String label) => Expanded(
        child: Container(
          key: ValueKey(key),
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
          decoration: BoxDecoration(
            color: MColors.primarySoft,
            borderRadius: BorderRadius.circular(MRadii.md),
          ),
          child: Column(
            children: [
              Text(value,
                  style: MFont.manrope(28, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 4),
              UiText(label,
                  style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
            ],
          ),
        ),
      );
}

class _Bars extends StatelessWidget {
  final List<int> values;
  const _Bars({required this.values});

  @override
  Widget build(BuildContext context) {
    final max = values.fold<int>(0, (m, v) => v > m ? v : m);
    return SizedBox(
      key: const ValueKey('progress-bars'),
      height: 96,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final v in values)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 1),
                child: Container(
                  height: v == 0 || max == 0 ? 3 : 3 + 93 * v / max,
                  decoration: BoxDecoration(
                    color: v == 0
                        ? MColors.muted.withValues(alpha: 0.25)
                        : MColors.primary,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
