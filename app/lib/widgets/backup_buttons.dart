import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/app_backup.dart';
import '../theme/mobile_theme.dart';
import 'mobile/common.dart';

/// 設定 → 資料: 匯出備份 / 從備份還原 (問題回報 #278). Export writes one
/// file and hands it to the share sheet (存到檔案、雲端硬碟、傳給自己);
/// restore picks such a file and replaces the learner's data with it.
class BackupButtons extends StatefulWidget {
  const BackupButtons({super.key});

  @override
  State<BackupButtons> createState() => _BackupButtonsState();
}

class _BackupButtonsState extends State<BackupButtons> {
  String? _busy;

  static String _size(int bytes) => bytes >= 1024 * 1024
      ? '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB'
      : '${(bytes / 1024).ceil()} KB';

  String _fileName() {
    final d = DateTime.now();
    String two(int v) => v.toString().padLeft(2, '0');
    return 'english_card_${d.year}${two(d.month)}${two(d.day)}_'
        '${two(d.hour)}${two(d.minute)}.${AppBackup.fileExtension}';
  }

  Future<void> _export() async {
    final scope = AppScope.of(context);
    final box = context.findRenderObject() as RenderBox?;
    final origin =
        box == null ? null : box.localToGlobal(Offset.zero) & box.size;
    setState(() => _busy = '正在建立備份…');
    try {
      final name = _fileName();
      final XFile file;
      final BackupSummary summary;
      if (kIsWeb) {
        final (bytes, s) = await AppBackup.toBytes(
            settings: scope.settings, photoStore: scope.photoStore);
        file = XFile.fromData(bytes,
            name: name, mimeType: 'application/octet-stream');
        summary = s;
      } else {
        // Written straight to a file, photo by photo.
        final dir = await getTemporaryDirectory();
        final path = '${dir.path}${Platform.pathSeparator}$name';
        final raf = await File(path).open(mode: FileMode.write);
        try {
          summary = await AppBackup.write(
              settings: scope.settings,
              photoStore: scope.photoStore,
              write: (b) => raf.writeFrom(b));
        } finally {
          await raf.close();
        }
        file = XFile(path, name: name, mimeType: 'application/octet-stream');
      }
      if (!mounted) return;
      setState(() => _busy = null);
      await SharePlus.instance.share(ShareParams(
        files: [file],
        fileNameOverrides: [name],
        subject: name,
        sharePositionOrigin: origin,
      ));
      if (mounted) {
        showToast(
            context,
            '已建立備份：${summary.words} 個單字、${summary.photos} 張照片、'
            '${summary.reviews} 筆複習紀錄（照片 ${_size(summary.photoBytes)}）');
      }
    } catch (e) {
      if (mounted) showToast(context, '備份失敗：$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _restore() async {
    final scope = AppScope.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const UiText('從備份還原？'),
        content: const UiText('還原會用備份檔取代目前所有的單字、照片、相片冊、複習紀錄與設定。'
            '想保留目前的資料，請先匯出備份。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('選擇備份檔')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final picked = await FilePicker.pickFile();
    if (picked == null || !mounted) return;
    setState(() => _busy = '正在還原…');
    try {
      final summary = await AppBackup.restore(picked.xFile.openRead(),
          settings: scope.settings, photoStore: scope.photoStore);
      await scope.reloadData?.call();
      if (mounted) {
        showToast(
            context,
            '已還原：${summary.words} 個單字、${summary.photos} 張照片、'
            '${summary.reviews} 筆複習紀錄');
      }
    } on BackupException catch (e) {
      if (mounted) showToast(context, e.message);
    } catch (e) {
      if (mounted) showToast(context, '還原失敗：$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final busy = _busy;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(spacing: 8, children: [
          TextButton(
              onPressed: busy == null ? _export : null,
              child: const UiText('匯出備份')),
          TextButton(
              onPressed: busy == null ? _restore : null,
              child: const UiText('從備份還原')),
        ]),
        if (busy != null)
          UiText(busy, style: MFont.manrope(12, FontWeight.w700, MColors.muted))
        else
          UiText('備份檔包含單字、照片、相片冊、複習紀錄與設定。',
              style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
      ],
    );
  }
}
