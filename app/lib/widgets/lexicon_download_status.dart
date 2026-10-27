import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../services/dictionary_sync.dart';
import '../services/lexicon_pack.dart';
import '../theme/mobile_theme.dart';

/// 問題回報 #856: on a fresh install the pack (~62 MB, 18,288 words, 10,720
/// pictures) arrives in the first minutes. Until it is in, the 資料庫 pages
/// say so instead of 「null 筆」, 「沒有符合的單字」 or an empty grid.
bool lexiconPending([LexiconPack? pack]) =>
    !(pack ?? LexiconPack.instance).hasCatalog;

/// The download failed and nothing is running now: the page shows the
/// friendly retry (status + 重新連線) instead of the progress.
bool lexiconDownloadFailed([DictionarySync? sync]) {
  final s = sync ?? DictionarySync.instance;
  return s.hasError && !s.downloading;
}

/// 「已下載 12 / 62 MB（19%）」, or null before the first byte arrives.
String? lexiconProgressText([DictionarySync? sync]) {
  final s = sync ?? DictionarySync.instance;
  if (!s.downloading || s.downloadedBytes <= 0) return null;
  String mb(int bytes) => (bytes / 1000000).toStringAsFixed(0);
  final total = s.downloadTotalBytes;
  if (total == null) return '已下載 ${mb(s.downloadedBytes)} MB';
  final percent = (s.downloadedBytes * 100 / total).clamp(0, 100).floor();
  return '已下載 ${mb(s.downloadedBytes)} / ${mb(total)} MB（$percent%）';
}

/// The progress card shown while [lexiconPending]; on a failed download the
/// existing retry card (問題回報 #856). Rebuild it from a listener on
/// [LexiconPack.instance] and [DictionarySync.instance].
class LexiconDownloadCard extends StatelessWidget {
  const LexiconDownloadCard({super.key});

  @override
  Widget build(BuildContext context) {
    final sync = DictionarySync.instance;
    final failed = lexiconDownloadFailed(sync);
    final progress = lexiconProgressText(sync);
    final total = sync.downloadTotalBytes;
    return Container(
      padding: const EdgeInsets.all(MSpace.lg),
      decoration: MDecor.emptyStateCard(),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (failed)
          const Icon(Icons.cloud_off_rounded, size: 36, color: MColors.muted)
        else
          SizedBox(
            width: 220,
            child: LinearProgressIndicator(
                key: const ValueKey('lexicon-download-progress'),
                value: progress != null && total != null
                    ? (sync.downloadedBytes / total).clamp(0.0, 1.0)
                    : null,
                color: MColors.primary),
          ),
        const SizedBox(height: MSpace.md),
        UiText(failed ? '正在取得資料庫內容' : '詞庫下載中（約 62 MB）',
            textAlign: TextAlign.center, style: MFont.titleSm),
        if (failed) ...[
          const SizedBox(height: MSpace.xs),
          Text(sync.status,
              textAlign: TextAlign.center, style: MFont.bodyMuted),
          const SizedBox(height: MSpace.md),
          ElevatedButton(onPressed: sync.refresh, child: const UiText('重新連線')),
        ] else if (progress != null) ...[
          const SizedBox(height: MSpace.xs),
          UiText(progress, textAlign: TextAlign.center, style: MFont.bodyMuted),
        ],
      ]),
    );
  }
}

/// Grey tiles where the lexicon pictures will be, with the note that they
/// come with the pack (問題回報 #856).
class LexiconPicturePlaceholders extends StatelessWidget {
  final double tileExtent;
  final EdgeInsetsGeometry padding;
  const LexiconPicturePlaceholders(
      {super.key,
      this.tileExtent = 230,
      this.padding = const EdgeInsets.all(MSpace.md)});

  @override
  Widget build(BuildContext context) => GridView.builder(
        key: const ValueKey('lexicon-picture-placeholders'),
        padding: padding,
        itemCount: 6,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisExtent: tileExtent,
            mainAxisSpacing: MSpace.sm,
            crossAxisSpacing: MSpace.sm),
        itemBuilder: (context, index) => Container(
          decoration: MDecor.emptyStateCard(),
          padding: const EdgeInsets.all(MSpace.md),
          alignment: Alignment.center,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.image_outlined, size: 32, color: MColors.muted),
            const SizedBox(height: MSpace.xs),
            UiText('圖片會隨詞庫一起下載',
                textAlign: TextAlign.center, style: MFont.caption),
          ]),
        ),
      );
}
