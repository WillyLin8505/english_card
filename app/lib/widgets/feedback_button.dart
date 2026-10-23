import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/card_report.dart';
import '../services/feedback_context.dart';
import '../theme/mobile_theme.dart';

/// 問題回報 #587: a small 意見回饋 button on every page. It floats above the
/// whole app (tabs, pushed screens, 新手引導), so each screen gets it without
/// carrying its own copy. [navigatorKey] is the app's root navigator, which
/// the form opens on.
class FeedbackOverlay extends StatelessWidget {
  final GlobalKey<NavigatorState> navigatorKey;
  final Widget child;
  final CardReportService? service;

  const FeedbackOverlay(
      {super.key,
      required this.navigatorKey,
      required this.child,
      this.service});

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    return Stack(
      children: [
        Positioned.fill(child: child),
        Positioned(
          right: 6,
          top: top + 2,
          child: Semantics(
            button: true,
            label: ui(context, '意見回饋'),
            child: Material(
              color: MColors.surface.withValues(alpha: 0.9),
              shape: const CircleBorder(),
              elevation: 1,
              child: InkWell(
                key: const ValueKey('feedback-button'),
                customBorder: const CircleBorder(),
                onTap: () {
                  final ctx = navigatorKey.currentContext;
                  if (ctx != null) showFeedbackDialog(ctx, service: service);
                },
                child: const Padding(
                  padding: EdgeInsets.all(5),
                  child: Icon(Icons.rate_review_outlined,
                      size: 16, color: MColors.muted),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The 意見回饋 form: one text box. Page, word/photo id, app version and
/// learning language are attached; it goes through the 卡片回報 offline queue.
Future<bool?> showFeedbackDialog(BuildContext context,
    {CardReportService? service}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  final fc = FeedbackContext.instance;
  final page = fc.page;
  final subject = fc.subject;
  final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
  final sink = service ?? CardReportService.instance;
  final language = scope?.settings.learningLanguage ?? '';
  final apiKey = scope?.settings.apiKey ?? '';
  return showDialog<bool>(
    context: context,
    builder: (_) => _FeedbackDialog(
        page: page,
        subject: subject,
        language: language,
        apiKey: apiKey,
        service: sink),
  ).then((sent) {
    if (sent == null) return null;
    messenger?.removeCurrentSnackBar();
    messenger?.showSnackBar(
        SnackBar(content: UiText(sent ? '已送出，謝謝你的意見' : '已存在這支手機，連上網路後會再送出')));
    return sent;
  });
}

class _FeedbackDialog extends StatefulWidget {
  final String page, language, apiKey;
  final String? subject;
  final CardReportService service;

  const _FeedbackDialog({
    required this.page,
    required this.language,
    required this.apiKey,
    required this.service,
    this.subject,
  });

  @override
  State<_FeedbackDialog> createState() => _FeedbackDialogState();
}

class _FeedbackDialogState extends State<_FeedbackDialog> {
  final _note = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final note = _note.text.trim();
    if (note.isEmpty) return;
    setState(() => _sending = true);
    final sent = await widget.service.submitIssue(
      feedbackIssue(
          page: widget.page,
          note: note,
          subject: widget.subject,
          language: widget.language),
      apiKey: widget.apiKey,
    );
    if (mounted) Navigator.of(context).pop(sent);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const UiText('意見回饋'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                key: const ValueKey('feedback-note'),
                controller: _note,
                autofocus: true,
                minLines: 3,
                maxLines: 6,
                maxLength: 500,
                decoration: const InputDecoration(border: OutlineInputBorder()),
              ),
              UiText('會一併附上目前頁面、App 版本與學習語言。',
                  style: MFont.inter(12, FontWeight.w500, MColors.label)),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: _sending ? null : () => Navigator.of(context).pop(),
              child: const UiText('取消')),
          FilledButton(
              onPressed: _sending ? null : _send, child: const UiText('送出')),
        ],
      );
}

/// The issue JSON for [showFeedbackDialog]: "[意見回饋] <頁面>：<前 30 字>".
Map<String, dynamic> feedbackIssue({
  required String page,
  required String note,
  String? subject,
  String language = '',
}) {
  final text = note.trim();
  final head = text.characters.take(30).toString();
  return {
    'kind': 'todo',
    'severity': 'medium',
    'area': 'app',
    'title': '[意見回饋] $page：$head',
    'detail': [
      '意見：$text',
      '頁面：$page',
      if ((subject ?? '').isNotEmpty) '單字／照片 id：$subject',
      'App 版本：${CardReport.appVersion}',
      if (language.isNotEmpty) '學習語言：$language',
    ].join('\n'),
    'reporter': 'App 使用者',
  };
}
