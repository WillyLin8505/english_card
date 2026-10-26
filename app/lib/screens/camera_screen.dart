import '../l10n/ui_text.dart';
import 'dart:math' as math;
import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../services/lexicon_pack.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../services/photo_store.dart';
import '../services/text_scan.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'photo_picker_screen.dart';

/// 圖辨單字 — Figma camera-view (11:6), the 拍照 tab: viewfinder, shutter,
/// 從相簿選擇 (gallery button) and flash.
///
/// The mock shows words pinned on the live view ("AI 實時辨識中"). The
/// tagger (spec section 2) works on a still photo, so here the shutter
/// captures, saves and tags the photo, and the words appear on 照片詳情;
/// the badge says what the camera and tagger are actually doing.
///
/// When no camera is available (desktop without a webcam, permission
/// denied) the viewfinder shows the newest photo and its words instead,
/// and says so.
///
/// The camera only runs while the 拍照 tab is showing ([ActiveTabScope]).
class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  bool _starting = false;
  String? _cameraError;
  bool _permissionDenied = false;
  bool _torch = false;
  bool _busy = false;
  bool _active = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Also false while another route covers this one in the tab.
    final active =
        (ActiveTabScope.of(context) ?? AppTab.camera) == AppTab.camera &&
            (ModalRoute.of(context)?.isCurrent ?? true);
    if (active == _active) return;
    _active = active;
    active ? _start() : _stop();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _stop();
    } else if (state == AppLifecycleState.resumed && _active) {
      _start();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  void _showPermissionHelp() {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const UiText('相機權限未開啟'),
        content: const UiText('請到手機「設定」→ 找到本 App → 開啟「相機」權限，再回來按「重試相機」。'),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              _start();
            },
            child: const UiText('重試相機'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const UiText('關閉'),
          ),
        ],
      ),
    );
  }

  Future<void> _start() async {
    if (_controller != null || _starting) return;
    _starting = true;
    _cameraError = null;
    _permissionDenied = false;
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw CameraException('none', '找不到相機');
      final camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller =
          CameraController(camera, ResolutionPreset.high, enableAudio: false);
      await controller.initialize();
      if (!mounted || !_active) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _cameraError = null;
      });
    } catch (e) {
      _cameraError = e is CameraException ? e.description ?? e.code : '$e';
      _permissionDenied = e is CameraException &&
          (e.code.startsWith('CameraAccess') || e.code.contains('Permission'));
      debugPrint('Camera unavailable: $_cameraError');
    } finally {
      _starting = false;
      if (mounted) setState(() {});
    }
  }

  void _stop() {
    final c = _controller;
    _controller = null;
    _torch = false;
    c?.dispose();
    if (mounted) setState(() {});
  }

  void _openPicker() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => const PhotoPickerScreen(),
      ));

  Future<void> _capture() async {
    final c = _controller;
    if (c == null || !c.value.isInitialized) {
      _openPicker();
      return;
    }
    if (_busy) return;
    final scope = AppScope.of(context);
    setState(() => _busy = true);
    try {
      final shot = await c.takePicture();
      final bytes = await shot.readAsBytes();
      if (!mounted) return;
      final now = scope.clock();
      final choice = await showSaveToAlbumDialog(
        context,
        repository: scope.repository,
        defaultTitle: defaultPhotoTitle(now),
      );
      if (choice == null) {
        if (mounted) showToast(context, '照片未儲存');
        return;
      }
      final photo = await scope.intake.addPhoto(bytes,
          title: choice.title,
          albumId: choice.albumId,
          scanMode: choice.scanMode);
      unawaited(scope.queue.process());
      scope.navigator.openPhoto(photo.id);
    } catch (e) {
      if (mounted) showToast(context, photoErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleTorch() async {
    final c = _controller;
    if (c == null) {
      showToast(context, '相機未啟用');
      return;
    }
    try {
      await c.setFlashMode(_torch ? FlashMode.off : FlashMode.torch);
      setState(() => _torch = !_torch);
    } catch (e) {
      debugPrint('Flash toggle failed: $e');
      if (mounted) showToast(context, '這台裝置不支援閃光燈');
    }
  }

  void _openLatest(Photo? latest) {
    // No photo yet: the chip reads 「先選一張照片開始學習」, so open the
    // picker instead of only telling the learner to take one.
    if (latest == null) return _openPicker();
    AppScope.of(context).navigator.openPhoto(latest.id);
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: Listenable.merge([repo, scope.settings, scope.queue]),
      builder: (context, _) {
        final latest = repo.photos.where(PhotoStore.canShow).firstOrNull;
        final String badge;
        if (_busy) {
          badge =
              scope.settings.taggingConfigured ? '正在找照片裡的單字…' : '正在讀照片裡的文字…';
        } else if (_controller == null) {
          badge = _cameraError != null
              ? (_permissionDenied ? '相機權限未開啟' : '目前無法使用相機')
              : _starting
                  ? '正在開啟相機…'
                  : '相機未啟用';
        } else {
          // Say the limit, not the capability: with only on-device text
          // scanning a cup or a plant finds nothing (問題回報 #472).
          badge = !scope.settings.taggingConfigured
              ? (TextScan.available ? '只找照片裡的{L}字・物品辨識未連線' : '照片辨識尚未連線')
              : scope.queue.offline
                  ? 'AI 離線 · 照片會先排隊'
                  : 'AI 辨識就緒';
        }

        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: GestureDetector(
              onVerticalDragEnd: (d) {
                if ((d.primaryVelocity ?? 0) < -300) _openLatest(latest);
              },
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: MSpace.xl, vertical: MSpace.md),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              UiText('拍照學單字', style: MFont.display),
                              const SizedBox(height: MSpace.xxs),
                              UiText('拍照或選一張照片，找出生活中的{L}單字',
                                  style: MFont.caption),
                            ],
                          ),
                        ),
                        NavIconButton(
                          label: '設定',
                          background: MColors.surface,
                          bordered: true,
                          icon: const MSvg(MIcon.settings20, size: 20),
                          onTap: () =>
                              scope.navigator.selectTab(AppTab.settings),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: Padding(
                      padding:
                          const EdgeInsets.symmetric(horizontal: MSpace.xl),
                      child: Container(
                        decoration: MDecor.heroPhotoFrame(),
                        clipBehavior: Clip.hardEdge,
                        child: _Viewfinder(
                          controller: _controller,
                          fallback: latest,
                          cameraError: _cameraError,
                          badge: badge,
                          onBadgeTap: _controller != null &&
                                  !_busy &&
                                  !scope.settings.taggingConfigured
                              ? () => scope.navigator.selectTab(AppTab.settings)
                              : null,
                          onOpenFallback: () => _openLatest(latest),
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: MSpace.xl, vertical: MSpace.lg),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: _controller == null
                              ? MainAxisAlignment.center
                              : MainAxisAlignment.spaceBetween,
                          children: [
                            // Without a camera the big middle button is the
                            // one 選擇照片 entry; gallery and flash are hidden
                            // (問題回報 #402).
                            if (_controller != null)
                              _RoundButton(
                                label: '從相簿選擇',
                                icon: MIcon.gallery20,
                                onTap: _openPicker,
                              ),
                            Tap(
                              onTap: _capture,
                              label: _controller == null ? '選擇照片' : '拍照',
                              child: Container(
                                width: 76,
                                height: 76,
                                decoration: BoxDecoration(
                                  color: MColors.primarySoft,
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color:
                                        MColors.primary.withValues(alpha: 0.25),
                                    width: 2,
                                  ),
                                ),
                                child: Center(
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    width: 58,
                                    height: 58,
                                    decoration: BoxDecoration(
                                      color: _busy
                                          ? MColors.primary
                                              .withValues(alpha: 0.6)
                                          : MColors.primary,
                                      shape: BoxShape.circle,
                                      boxShadow: MShadows.primaryGlow,
                                    ),
                                    child: Center(
                                      child: MSvg(
                                        _controller == null
                                            ? MIcon.gallery20
                                            : MIcon.cameraWhite,
                                        size: 24,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            if (_controller != null)
                              _RoundButton(
                                label: _torch ? '關閉閃光燈' : '開啟閃光燈',
                                icon: MIcon.zap,
                                highlighted: _torch,
                                onTap: _toggleTorch,
                              ),
                          ],
                        ),
                        // With a camera, the badge and the top-right settings
                        // button already lead to setup; this panel is only
                        // the fallback when there is no camera (問題回報 #535).
                        if (_controller == null) ...[
                          const SizedBox(height: MSpace.sm),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: MSpace.sm, vertical: MSpace.xxs),
                            decoration: MDecor.softPanel(),
                            child: Wrap(
                              alignment: WrapAlignment.center,
                              spacing: MSpace.xs,
                              runSpacing: MSpace.xxs,
                              children: [
                                if (_controller == null) ...[
                                  TextButton.icon(
                                    onPressed: _starting
                                        ? null
                                        : _permissionDenied
                                            ? _showPermissionHelp
                                            : _start,
                                    icon: const MSvg(MIcon.pulseDot, size: 16),
                                    label: UiText(
                                        _permissionDenied ? '開啟權限說明' : '重試相機'),
                                  ),
                                ],
                                if (!scope.settings.taggingConfigured) ...[
                                  TextButton.icon(
                                    onPressed: () => scope.navigator
                                        .selectTab(AppTab.settings),
                                    icon:
                                        const MSvg(MIcon.settings20, size: 16),
                                    label: const UiText('設定辨識'),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ],
                        // Owner: no 「先選一張照片開始學習」 chip before the first
                        // photo (問題回報 #613); the picker button stays.
                        if (latest != null) ...[
                          const SizedBox(height: MSpace.md),
                          Tap(
                            onTap: () => _openLatest(latest),
                            label: '查看最近照片的單字',
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: MSpace.md,
                                  vertical: MSpace.xs + 2),
                              constraints: const BoxConstraints(
                                  minWidth: 48, minHeight: 48),
                              decoration: MDecor.chipSurface(active: true),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const MSvg(MIcon.chevronUp, size: 16),
                                  const SizedBox(width: MSpace.xs),
                                  // Flexible: the English and French copy is
                                  // longer than the Chinese (問題回報 #363).
                                  Flexible(
                                    child: UiText(
                                        // With a live preview behind the button,
                                        // 「這張」 reads as the viewfinder; it
                                        // opens the last photo (問題回報 #583).
                                        _controller?.value.isInitialized == true
                                            ? '最近一張照片的單字'
                                            : '查看這張照片的單字',
                                        textAlign: TextAlign.center,
                                        style: MFont.manrope(13,
                                            FontWeight.w700, MColors.primary)),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _RoundButton extends StatelessWidget {
  final String label;
  final MIcon icon;
  final bool highlighted;
  final VoidCallback onTap;

  const _RoundButton({
    required this.label,
    required this.icon,
    required this.onTap,
    this.highlighted = false,
  });

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: label,
        child: Container(
          width: 50,
          height: 50,
          decoration: MDecor.card(
            color: highlighted ? MColors.primarySoft : MColors.surface,
            borderColor: highlighted
                ? MColors.primary.withValues(alpha: 0.3)
                : MColors.borderSoft,
            radius: MRadii.pill,
            shadow: MShadows.soft,
          ),
          child: Center(
            child: MSvg(
              icon,
              size: 20,
              tint: highlighted ? MColors.primary : null,
            ),
          ),
        ),
      );
}

/// Figma viewfinder (11:18): 24px corners, the AI badge top-left.
class _Viewfinder extends StatelessWidget {
  final CameraController? controller;
  final Photo? fallback;
  final String? cameraError;
  final String badge;

  /// Recognition not set up: the badge opens 設定 → 照片辨識.
  final VoidCallback? onBadgeTap;
  final VoidCallback onOpenFallback;

  const _Viewfinder({
    required this.controller,
    required this.fallback,
    required this.cameraError,
    required this.badge,
    this.onBadgeTap,
    required this.onOpenFallback,
  });

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final Widget content;
    if (c != null && c.value.isInitialized) {
      final size = c.value.previewSize;
      final w = size == null ? 300.0 : math.min(size.width, size.height);
      final h = size == null ? 400.0 : math.max(size.width, size.height);
      content = SizedBox.expand(
        child: FittedBox(
          fit: BoxFit.cover,
          clipBehavior: Clip.hardEdge,
          child: SizedBox(width: w, height: h, child: CameraPreview(c)),
        ),
      );
    } else if (fallback != null) {
      final repo = AppScope.of(context).repository;
      content = Tap(
        onTap: onOpenFallback,
        label: '開啟最近的照片',
        child: PinnedPhoto(
          photo: fallback!,
          radius: 0,
          largePins: true,
          // Clear of the status chip, and of the notice when there's no camera.
          reserveTop: 52,
          reserveBottom: c == null ? 84 : 0,
          pins: [
            for (final l in repo.visibleLabels(fallback!.id))
              if (l.occ.placed)
                PinData(
                    id: l.occ.id,
                    anchor: l.occ.anchor,
                    word: shownWord(l.entry.word, repo.language, pos: l.entry.pos),
                    zh: l.entry.meaning,
                    entryType: l.entry.entryType,
                    linked: l.entry.lexemeId != null ||
                        LexiconPack.instance.isEmpty),
          ],
        ),
      );
    } else {
      content = ColoredBox(
        color: MColors.surfaceSoft,
        child: Center(
          child: UiText(
            '尚未有可用相機或照片',
            style: MFont.manrope(14, FontWeight.w600, MColors.muted),
          ),
        ),
      );
    }

    return ClipRRect(
      borderRadius: MRadii.rXxl,
      child: Stack(
        children: [
          Positioned.fill(child: content),
          Positioned(
            left: MSpace.lg,
            top: MSpace.lg,
            right: MSpace.lg,
            child: Align(
              alignment: Alignment.centerLeft,
              child: Tap(
                onTap: onBadgeTap,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: MSpace.sm, vertical: MSpace.xxs),
                  decoration: MDecor.overlayPill(
                    color: MColors.ink.withValues(alpha: 0.75),
                    radius: MRadii.xl,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const MSvg(MIcon.pulseDot, size: 8),
                      const SizedBox(width: MSpace.xxs),
                      Flexible(
                        child: UiText(badge,
                            style: MFont.manrope(
                                12, FontWeight.w700, Colors.white)),
                      ),
                      if (onBadgeTap != null) ...[
                        const SizedBox(width: MSpace.xxs),
                        const Icon(Icons.chevron_right_rounded,
                            size: 14, color: Colors.white),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (c == null && cameraError != null)
            Positioned(
              left: MSpace.lg,
              right: MSpace.lg,
              bottom: MSpace.lg,
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: MSpace.md, vertical: MSpace.sm),
                decoration: MDecor.card(
                  color: MColors.surface.withValues(alpha: 0.95),
                  radius: MRadii.md,
                  shadow: MShadows.card,
                ),
                child: UiText(
                  fallback != null
                      ? '${fallback!.assetPath != null ? '範例照片' : '最近的照片'}：點照片看單字，或按下方「選擇照片」。'
                      : '你可以按下方「選擇照片」，開始學單字。',
                  style: MFont.manrope(12, FontWeight.w600, MColors.ink),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
