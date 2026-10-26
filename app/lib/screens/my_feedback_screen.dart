import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/card_report.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';

/// 設定 → 我的意見回饋 (問題回報 #701): the 意見回饋 and 卡片回報 this phone
/// sent or still has queued, newest first, each with its time, whether it
/// reached the server (and its 問題回報 number), and the screenshot.
/// Opening the page asks the server which reports are 處理中 or 已處理
/// (問題回報 #728). Deleting a sent one deletes its 問題回報 too (#716); a
/// queued one is not sent any more.
class MyFeedbackScreen extends StatefulWidget {
  final CardReportService? service;

  const MyFeedbackScreen({super.key, this.service});

  @override
  State<MyFeedbackScreen> createState() => _MyFeedbackScreenState();
}

class _MyFeedbackScreenState extends State<MyFeedbackScreen> {
  late final CardReportService _service =
      widget.service ?? CardReportService.instance;
  List<FeedbackRecord>? _records;
  bool _asked = false;

  String get _apiKey =>
      context.getInheritedWidgetOfExactType<AppScope>()?.settings.apiKey ?? '';

  @override
  void initState() {
    super.initState();
    _service.addListener(_reload);
    _reload();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_asked) return;
    _asked = true;
    // 問題回報 #728: fresh 處理中／已處理 each time the page opens; quiet
    // when the server can't say.
    _service.refreshStatus(apiKey: _apiKey);
  }

  @override
  void dispose() {
    _service.removeListener(_reload);
    super.dispose();
  }

  Future<void> _reload() async {
    final records = await _service.history();
    if (mounted) setState(() => _records = records);
  }

  Future<void> _delete(FeedbackRecord r) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const UiText('刪除這筆紀錄？'),
        content: UiText(r.queued
            ? '還沒送出的會取消，不會再送出。'
            : r.issueNo != null
                ? '會從這支手機和問題回報一起刪除。'
                : '只會從這支手機移除，已送到問題回報的不會刪除。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          FilledButton(
              key: const ValueKey('feedback-delete-confirm'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('刪除')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    if (await _service.delete(r.id, apiKey: _apiKey) || !mounted) return;
    // 問題回報 #716: the server kept it (offline, no key), so keep it here
    // too unless the learner only wants it off this phone.
    final local = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const UiText('沒辦法從問題回報刪除'),
        content: const UiText('伺服器沒有刪掉這筆回報，紀錄先留在這支手機。可以稍後再試。'),
        actions: [
          TextButton(
              key: const ValueKey('feedback-delete-local'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const UiText('只從這支手機移除')),
          FilledButton(
              key: const ValueKey('feedback-delete-keep'),
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('先留著')),
        ],
      ),
    );
    if (local == true) await _service.delete(r.id, localOnly: true);
  }

  /// 問題回報 #728: 處理中／已處理 once the server has said, else 已送出.
  static String _state(FeedbackRecord r) {
    if (r.queued) return '還在排隊，連上網路後會送出';
    final no = r.issueNo;
    if (no == null) return '已送出';
    return switch (r.handled) {
      true => '已處理 · #$no',
      false => '處理中 · #$no',
      null => '已送出 · #$no',
    };
  }

  static String _time(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${t.year}/${two(t.month)}/${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final records = _records;
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            MNavBar(
              title: '我的意見回饋',
              leading: BackNavButton(onTap: () => Navigator.of(context).pop()),
            ),
            Expanded(
              child: records == null
                  ? const Center(child: CircularProgressIndicator())
                  : ListView(
                      padding: const EdgeInsets.all(MSpace.lg),
                      children: [
                        UiText(
                            '這支手機送過的意見回饋與卡片回報，以及處理進度。刪除已送出的會連問題回報一起刪除；還沒送出的就不會送出。',
                            style: MFont.manrope(
                                13, FontWeight.w600, MColors.muted)),
                        const SizedBox(height: 12),
                        if (records.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 32),
                            child: UiText('還沒有送過意見回饋',
                                textAlign: TextAlign.center,
                                style: MFont.manrope(
                                    15, FontWeight.w700, MColors.muted)),
                          ),
                        for (final r in records) _row(r),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(FeedbackRecord r) {
    final shot = r.screenshotBytes;
    return Container(
      key: ValueKey('feedback-record-${r.id}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: MColors.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (shot != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.memory(shot,
                  key: ValueKey('feedback-thumb-${r.id}'),
                  width: 48,
                  height: 72,
                  cacheHeight: 144,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      const SizedBox(width: 48, height: 72)),
            ),
            const SizedBox(width: 10),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // The title is what was sent, in the learner's own words.
                Text(r.title,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: MFont.manrope(14, FontWeight.w700, MColors.ink)),
                const SizedBox(height: 4),
                Text(_time(r.createdAt),
                    style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
                const SizedBox(height: 2),
                UiText(_state(r),
                    key: ValueKey('feedback-state-${r.id}'),
                    style: MFont.manrope(
                        12,
                        FontWeight.w700,
                        r.queued
                            ? MColors.muted
                            : r.handled == false
                                ? MColors.primary
                                : MColors.success)),
              ],
            ),
          ),
          IconButton(
            key: ValueKey('feedback-delete-${r.id}'),
            tooltip: ui(context, '刪除'),
            icon: const Icon(Icons.delete_outline, color: MColors.muted),
            onPressed: () => _delete(r),
          ),
        ],
      ),
    );
  }
}
