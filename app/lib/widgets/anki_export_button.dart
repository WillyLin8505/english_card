import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../models/photo.dart';
import '../services/anki_export.dart';
import '../services/deck_library.dart';
import '../services/lexicon_pack.dart';
import '../theme/mobile_theme.dart';
import 'mobile/common.dart';

/// 設定 → 資料 → 匯出到 Anki (問題回報 #325): pick 全部單字, an album or
/// an installed 卡片集, build the zip ([AnkiExport]) and hand it to the
/// share sheet.
class AnkiExportButton extends StatefulWidget {
  const AnkiExportButton({super.key, this.decks});

  /// Installed decks; defaults to [DeckLibrary.instance] (tests pass one).
  final DeckLibrary? decks;

  @override
  State<AnkiExportButton> createState() => _AnkiExportButtonState();
}

class _AnkiExportButtonState extends State<AnkiExportButton> {
  bool _busy = false;

  Future<AnkiExportScope?> _pickScope() async {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final decks = widget.decks ?? DeckLibrary.instance;
    try {
      await decks.load(repo.language);
    } catch (_) {
      // No deck list on this device: albums and 全部單字 still work.
    }
    if (!mounted) return null;
    final options = <(String, AnkiExportScope)>[
      ('全部單字（${repo.wordCount}）', const AnkiExportScope.all()),
      for (final a in repo.albums)
        ('相簿：${a.name}', AnkiExportScope.album(a)),
      for (final d in decks.installed)
        ('卡片集：${d.info.title}', AnkiExportScope.deck(d)),
    ];
    return showDialog<AnkiExportScope>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const UiText('匯出到 Anki：選擇範圍'),
        children: [
          for (final (label, s) in options)
            SimpleDialogOption(
              onPressed: () => Navigator.of(context).pop(s),
              child: UiText(label),
            ),
        ],
      ),
    );
  }

  Future<void> _export() async {
    final scope = AppScope.of(context);
    final box = context.findRenderObject() as RenderBox?;
    final origin =
        box == null ? null : box.localToGlobal(Offset.zero) & box.size;
    final picked = await _pickScope();
    if (picked == null || !mounted) return;
    setState(() => _busy = true);
    try {
      Future<Uint8List?> photoBytes(Photo p) async {
        if (p.filePath != null && !kIsWeb) {
          final f = File(p.filePath!);
          if (await f.exists()) return f.readAsBytes();
        }
        if (p.storedKey != null) return scope.photoStore.storedBytes(p.storedKey!);
        if (p.assetPath != null) return assetBytes(p.assetPath!);
        return null;
      }

      final result = await AnkiExport.build(
        repository: scope.repository,
        scope: picked,
        photoBytes: photoBytes,
        assetBytes: assetBytes,
        lexeme: LexiconPack.instance.byId,
      );
      if (!mounted) return;
      if (result.notes == 0) {
        showToast(context, '這個範圍沒有單字可以匯出');
        return;
      }
      final d = DateTime.now();
      String two(int v) => v.toString().padLeft(2, '0');
      final name = 'english_card_anki_${d.year}${two(d.month)}${two(d.day)}.zip';
      final XFile file;
      if (kIsWeb) {
        file = XFile.fromData(result.bytes, name: name, mimeType: 'application/zip');
      } else {
        final dir = await getTemporaryDirectory();
        final path = '${dir.path}${Platform.pathSeparator}$name';
        await File(path).writeAsBytes(result.bytes);
        file = XFile(path, name: name, mimeType: 'application/zip');
      }
      setState(() => _busy = false);
      await SharePlus.instance.share(ShareParams(
        files: [file],
        fileNameOverrides: [name],
        subject: name,
        sharePositionOrigin: origin,
      ));
      if (mounted) {
        showToast(
            context,
            '已匯出 ${result.notes} 張卡、${result.photos} 張照片、'
            '${result.audio} 個音檔。解壓縮後照「匯入說明.txt」匯入 Anki');
      }
    } catch (e) {
      if (mounted) showToast(context, '匯出失敗：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static Future<Uint8List?> assetBytes(String path) async {
    try {
      final data = await rootBundle.load(path);
      return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextButton(
            onPressed: _busy ? null : _export,
            child: const UiText('匯出到 Anki')),
        UiText(
            _busy
                ? '正在建立 Anki 匯入檔…'
                : '把單字卡連同照片和發音存成 Anki 檔，可以存到檔案或傳到其他 App。',
            style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
      ],
    );
  }
}
