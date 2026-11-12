import 'package:flutter/material.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

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
  static const _buttonHeight = 44.0;
  bool _busy = false;

  CloudBackup get _cloud => widget.cloud ?? CloudBackup(widget.settings);

  Future<void> _run(Future<void> Function() job) async {
    setState(() => _busy = true);
    try {
      await job();
      if (mounted && widget.settings.cloudSignedIn) {
        showToast(context, '已登入 ${widget.settings.cloudEmail}');
        await askAccountStats(context, widget.settings);
        if (!mounted) return;
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
        if (c != null) {
          await _cloud.loginWithApple(c.token,
              name: c.name, authorizationCode: c.authorizationCode);
        }
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
            SizedBox(
                height: _buttonHeight,
                child: OutlinedButton(
                    key: const Key('signInGoogle'),
                    onPressed: _busy ? null : _google,
                    child: const UiText('用 Google 繼續'))),
          // Apple's official button (HIG / App Review 4.8): same height as Google's.
          if (widget.social.appleAvailable)
            SignInWithAppleButton(
                key: const Key('signInApple'),
                height: _buttonHeight,
                text: ui(context, '使用 Apple 登入'),
                onPressed: () {
                  if (!_busy) _apple();
                }),
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

/// 卡 #1009: the first sign-in asks once whether the daily usage numbers may go to
/// the account. Nothing is sent before a yes; an earlier answer is kept.
Future<void> askAccountStats(BuildContext context, AppSettings settings) async {
  if (settings.accountStatsChoice != null) return;
  final allow = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) => AlertDialog(
      title: const UiText('把使用數字送到我的帳號？'),
      content: const UiText(
          '每天最多一次，把已安裝的單字牌組與相片冊名稱、學習語言、單字數，以及複習與拍照的次數送到你的帳號。管理者會看到你用了哪些資料庫；不含單字內容、照片或位置。可以隨時在「設定 → 隱私」關閉，關閉後伺服器上的這筆數字會被刪除。'),
      actions: [
        TextButton(
            key: const ValueKey('account-stats-deny'),
            onPressed: () => Navigator.pop(context, false),
            child: const UiText('不要')),
        TextButton(
            key: const ValueKey('account-stats-allow'),
            onPressed: () => Navigator.pop(context, true),
            child: const UiText('允許')),
      ],
    ),
  );
  // The first report goes out at the next start (UsageReport.sendIfDue).
  settings.accountStats = allow == true;
}
