import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../services/lexicon_pack.dart';
import '../theme/mobile_theme.dart';

/// 問題回報 #657 (M138): a CC BY-SA recording names its speaker and license
/// where it is played — 「發音錄音：Speaker · CC BY-SA 4.0（commons.wikimedia.org）」.
class RecordingCreditLine extends StatelessWidget {
  final RecordingCredit credit;

  const RecordingCreditLine(this.credit, {super.key});

  static String label(RecordingCredit credit) {
    // 卡 #695: an Azure clip is credited as a synthetic voice, as is.
    if (credit.isSynthetic) return credit.text;
    final host = credit.sourcePage == null
        ? null
        : Uri.tryParse(credit.sourcePage!)?.host;
    return '發音錄音：${credit.text}'
        '${host == null || host.isEmpty ? '' : '（$host）'}';
  }

  @override
  Widget build(BuildContext context) => UiText(label(credit),
      key: const ValueKey('recording-credit'),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: MFont.manrope(11, FontWeight.w600, MColors.label));
}
