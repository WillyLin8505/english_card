import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/app_backup.dart';
import '../services/cloud_backup.dart';
import '../services/cloud_sync.dart';
import '../theme/mobile_theme.dart';
import 'account_sign_in.dart';
import 'mobile/common.dart';

/// 設定 → 資料: 雲端備份 (card #902, 問題回報 #1173). Sign in (Google, Apple or email; card #910), then
/// 備份到雲端 / 從雲端還原 keeps the learner's data under the account so a new
/// phone (or a re-installed App) gets it back.
class CloudBackupButtons extends StatefulWidget {
  const CloudBackupButtons({super.key});

  @override
  State<CloudBackupButtons> createState() => _CloudBackupButtonsState();
}

/// Status of 跨裝置自動同步 and its switches (card #912).
class CloudSyncPanel extends StatelessWidget {
  final CloudSync sync;
  const CloudSyncPanel({super.key, required this.sync});

  static String _two(int v) => v.toString().padLeft(2, '0');

  static String statusOf(CloudSync sync) {
    final waiting = sync.pendingRecords;
    switch (sync.state) {
      case CloudSyncState.off:
        return sync.settings.cloudSyncEnabled ? '尚未同步' : '自動同步已關閉';
      case CloudSyncState.syncing:
        return '正在同步…';
      case CloudSyncState.offline:
        return waiting > 0 ? '沒有網路，$waiting 筆改動連線後補傳' : '沒有網路，連線後會自動同步';
      case CloudSyncState.failed:
        return '同步失敗，稍後會自動重試';
      case CloudSyncState.needsUpdate:
        return '雲端資料來自較新版本，請先更新 App';
      case CloudSyncState.photoSpaceFull:
        return '雲端照片空間已滿，照片暫停上傳';
      case CloudSyncState.idle:
        final at = sync.lastSyncedAt;
        final done = at == null
            ? '已同步'
            : '已同步 ${_two(at.hour)}:${_two(at.minute)}';
        if (sync.photosWaitForWifi) {
          return '$done · ${sync.pendingPhotos} 張照片等 Wi-Fi';
        }
        return sync.pendingPhotos > 0
            ? '$done · 還有 ${sync.pendingPhotos} 張照片'
            : done;
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = sync.settings;
    final style = MFont.manrope(12, FontWeight.w600, MColors.muted);
    return ListenableBuilder(
      listenable: sync,
      builder: (context, _) {
        final retry = sync.state == CloudSyncState.failed ||
            sync.state == CloudSyncState.offline;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              key: const Key('cloudSyncEnabled'),
              contentPadding: EdgeInsets.zero,
              title: const UiText('自動同步到其他裝置'),
              value: settings.cloudSyncEnabled,
              onChanged: (v) {
                settings.cloudSyncEnabled = v;
                sync.syncSoon(Duration.zero);
              },
            ),
            SwitchListTile(
              key: const Key('syncPhotos'),
              contentPadding: EdgeInsets.zero,
              title: const UiText('同步照片'),
              value: settings.syncPhotos,
              onChanged: settings.cloudSyncEnabled
                  ? (v) {
                      settings.syncPhotos = v;
                      sync.syncSoon(Duration.zero);
                    }
                  : null,
            ),
            SwitchListTile(
              key: const Key('syncPhotosWifiOnly'),
              contentPadding: EdgeInsets.zero,
              title: const UiText('照片只用 Wi-Fi 傳'),
              value: settings.syncPhotosWifiOnly,
              onChanged: settings.cloudSyncEnabled && settings.syncPhotos
                  ? (v) {
                      settings.syncPhotosWifiOnly = v;
                      sync.syncSoon(Duration.zero);
                    }
                  : null,
            ),
            Row(children: [
              Expanded(
                  child: UiText(statusOf(sync),
                      key: const Key('cloudSyncStatus'), style: style)),
              TextButton(
                  key: const Key('cloudSyncNow'),
                  onPressed: sync.state == CloudSyncState.syncing ||
                          !settings.cloudSyncEnabled
                      ? null
                      : sync.syncNow,
                  child: UiText(retry ? '重試' : '立即同步')),
            ]),
          ],
        );
      },
    );
  }
}

class _CloudBackupButtonsState extends State<CloudBackupButtons> {
  String? _busy;
  String? _status;

  Future<void> _run(String busy, Future<String?> Function() job) async {
    setState(() => _busy = busy);
    try {
      final done = await job();
      if (mounted && done != null) showToast(context, done);
    } on CloudBackupException catch (e) {
      if (mounted) showToast(context, e.message);
    } on BackupException catch (e) {
      if (mounted) showToast(context, e.message);
    } catch (e) {
      if (mounted) showToast(context, '雲端連線失敗：$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _deleteAccount() async {
    final scope = AppScope.of(context);
    final cloud = CloudBackup(scope.settings);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const UiText('刪除帳號？'),
        content: const UiText('會刪除你的帳號和雲端備份，無法復原。這台裝置上的單字與照片不會被刪除。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          TextButton(
              key: const Key('confirmDeleteAccount'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('刪除帳號')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _run('正在刪除帳號…', () async {
      await cloud.deleteAccount();
      _status = null;
      return '帳號已刪除';
    });
  }

  Future<void> _upload() async {
    final scope = AppScope.of(context);
    final cloud = CloudBackup(scope.settings);
    await _run('正在備份到雲端…', () async {
      final BackupSummary summary;
      if (kIsWeb) {
        final (bytes, s) = await AppBackup.toBytes(
            settings: scope.settings, photoStore: scope.photoStore);
        await cloud.uploadBytes(bytes);
        summary = s;
      } else {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}${Platform.pathSeparator}cloud.backup');
        final raf = await file.open(mode: FileMode.write);
        try {
          summary = await AppBackup.write(
              settings: scope.settings,
              photoStore: scope.photoStore,
              write: (b) => raf.writeFrom(b));
        } finally {
          await raf.close();
        }
        try {
          await cloud.uploadFile(file);
        } finally {
          if (await file.exists()) await file.delete();
        }
      }
      _status = null;
      return '已備份到雲端：${summary.words} 個單字、${summary.photos} 張照片、'
          '${summary.reviews} 筆複習紀錄';
    });
  }

  Future<void> _download() async {
    final scope = AppScope.of(context);
    final cloud = CloudBackup(scope.settings);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const UiText('從雲端還原？'),
        content: const UiText('還原會用雲端備份取代這台裝置目前所有的單字、照片、相片冊、複習紀錄與設定。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('還原')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _run('正在從雲端還原…', () async {
      final BackupSummary summary;
      if (kIsWeb) {
        final bytes = await cloud.downloadBytes();
        summary = await AppBackup.restore(Stream.value(bytes),
            settings: scope.settings, photoStore: scope.photoStore);
      } else {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}${Platform.pathSeparator}cloud.restore');
        try {
          await cloud.downloadTo(file);
          summary = await AppBackup.restore(file.openRead(),
              settings: scope.settings, photoStore: scope.photoStore);
        } finally {
          if (await file.exists()) await file.delete();
        }
      }
      await scope.reloadData?.call();
      return '已從雲端還原：${summary.words} 個單字、${summary.photos} 張照片、'
          '${summary.reviews} 筆複習紀錄';
    });
  }

  Future<void> _check() async {
    final cloud = CloudBackup(AppScope.of(context).settings);
    await _run('正在查詢…', () async {
      final info = await cloud.info();
      final at = info.updatedAt;
      String two(int v) => v.toString().padLeft(2, '0');
      _status = info.exists && at != null
          ? '雲端備份：${at.year}/${two(at.month)}/${two(at.day)} '
              '${two(at.hour)}:${two(at.minute)}'
          : '雲端還沒有備份';
      return null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final settings = AppScope.of(context).settings;
    final cloud = CloudBackup(settings);
    if (!cloud.available) return const SizedBox.shrink();
    final busy = _busy;
    final style = MFont.manrope(12, FontWeight.w600, MColors.muted);
    if (!settings.cloudSignedIn) {
      return AccountSignInButtons(settings: settings);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (AppScope.of(context).cloudSync case final sync?)
          CloudSyncPanel(sync: sync),
        Wrap(spacing: 8, children: [
          TextButton(
              onPressed: busy == null ? _upload : null,
              child: const UiText('備份到雲端')),
          TextButton(
              onPressed: busy == null ? _download : null,
              child: const UiText('從雲端還原')),
          TextButton(
              onPressed: busy == null ? _check : null,
              child: const UiText('查看雲端備份')),
          TextButton(
              onPressed: busy == null
                  ? () => _run('正在登出…', () async {
                        await cloud.logout();
                        return '已登出';
                      })
                  : null,
              child: const UiText('登出')),
          TextButton(
              key: const Key('deleteAccount'),
              onPressed: busy == null ? _deleteAccount : null,
              child: const UiText('刪除帳號')),
        ]),
        UiText(busy ?? _status ?? '已登入：${settings.cloudEmail}', style: style),
      ],
    );
  }
}
