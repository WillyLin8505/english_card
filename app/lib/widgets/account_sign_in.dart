import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../services/app_settings.dart';
import '../services/cloud_backup.dart';
import '../services/social_sign_in.dart';
import '../theme/mobile_theme.dart';
import 'mobile/common.dart';

/// 登入入口 (card #910): 用 Google 繼續 / 使用 Apple 登入 / Email 登入 / 建立帳號.
/// Shared by 設定 → 資料 and the end of the first-run guide; always optional —
/// the App works fully without an account.
class AccountSignInButtons extends StatefulWidget {
  final AppSettings settings;
  final VoidCallback? onSignedIn;
  final SocialSignIn social;
  final CloudBackup? cloud;

  AccountSignInButtons(
      {super.key,
      required this.settings,
      this.onSignedIn,
      SocialSignIn? social,
      this.cloud})
      : social = social ?? PlatformSocialSignIn();

  @override
  State<AccountSignInButtons> createState() => _AccountSignInButtonsState();
}

class _AccountSignInButtonsState extends State<AccountSignInButtons> {
  bool _busy = false;

  CloudBackup get _cloud => widget.cloud ?? CloudBackup(widget.settings);

  Future<void> _run(Future<void> Function() job) async {
    setState(() => _busy = true);
    try {
      await job();
      if (mounted && widget.settings.cloudSignedIn) {
        showToast(context, '已登入 ${widget.settings.cloudEmail}');
        widget.onSignedIn?.call();
      }
    } on CloudBackupException catch (e) {
      if (mounted) showToast(context, e.message);
    } catch (e) {
      if (mounted) showToast(context, '登入失敗：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _google() => _run(() async {
        final c = await widget.social.google();
        if (c != null) await _cloud.loginWithGoogle(c.token, name: c.name);
      });

  Future<void> _apple() => _run(() async {
        final c = await widget.social.apple();
        if (c != null) await _cloud.loginWithApple(c.token, name: c.name);
      });

  Future<void> _email({required bool create}) async {
    final email = TextEditingController();
    final password = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: UiText(create ? '建立帳號' : '登入'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
              controller: email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email')),
          TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: '密碼（至少 8 個字）')),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const UiText('取消')),
          TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: UiText(create ? '建立' : '登入')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _run(() => create
        ? _cloud.register(email.text, password.text)
        : _cloud.login(email.text, password.text));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(spacing: 8, children: [
          if (widget.social.googleConfigured)
            OutlinedButton(
                key: const Key('signInGoogle'),
                onPressed: _busy ? null : _google,
                child: const UiText('用 Google 繼續')),
          if (widget.social.appleAvailable)
            OutlinedButton(
                key: const Key('signInApple'),
                onPressed: _busy ? null : _apple,
                child: const UiText('使用 Apple 登入')),
          TextButton(
              key: const Key('signInEmail'),
              onPressed: _busy ? null : () => _email(create: false),
              child: const UiText('用 Email 登入')),
          TextButton(
              key: const Key('signUpEmail'),
              onPressed: _busy ? null : () => _email(create: true),
              child: const UiText('建立帳號')),
        ]),
        UiText(_busy ? '正在連線…' : '登入後可把資料備份到雲端，換手機或重裝 App 後還原。不登入也能完整使用。',
            style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
      ],
    );
  }
}
