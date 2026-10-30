import '../l10n/ui_text.dart';
import 'dart:math' as math;
import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show HapticFeedback;

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
import '../services/text_scan.dart';
import 'photo_picker_screen.dart';

/// 圖辨單字 — Figma camera-view (11:6), the 拍照 tab: viewfinder, shutter,
/// 從相簿選擇 (gallery button) and the shutter.
///
/// The mock shows words pinned on the live view ("AI 實時辨識中"). The
/// tagger (spec section 2) works on a still photo, so here the shutter
/// captures, saves and tags the photo, and the words appear on 照片詳情;
/// the badge says what the camera and tagger are actually doing.
///
/// When no camera is available (desktop without a webcam, permission
/// denied) the viewfinder says so and points to 選擇照片.
///
/// Owner (問題回報 #727): coming back to 拍照 shows a clean camera, never the
/// last photo's words — no 「最近一張照片的單字」 pill and no last photo with
/// its pins behind the viewfinder. The shutter saves the photo to an album
/// before 照片詳情 opens, so nothing unsaved lives on this tab; the words are
/// in 相片冊.
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
  bool _busy = false;
  bool _active = false;
  bool _flashing = false;
  CameraLensDirection _lens = CameraLensDirection.back;

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
        (c) => c.lensDirection == _lens,
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
    c?.dispose();
    if (mounted) setState(() {});
  }

  void _openPicker() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => const PhotoPickerScreen(),
      ));

  /// 前／後鏡頭 (iPhone 相機式): restart the live view on the other lens.
  void _flip() {
    _lens = _lens == CameraLensDirection.back
        ? CameraLensDirection.front
        : CameraLensDirection.back;
    _stop();
    _start();
  }

  Future<void> _capture() async {
    final c = _controller;
    if (c == null || !c.value.isInitialized) {
      _openPicker();
      return;
    }
    if (_busy) return;
    final scope = AppScope.of(context);
    setState(() => _busy = true);
    // The iPhone-style flash and buzz on the press.
    HapticFeedback.mediumImpact();
    setState(() => _flashing = true);
    Future<void>.delayed(const Duration(milliseconds: 150), () {
      if (mounted) setState(() => _flashing = false);
    });
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

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: Listenable.merge([repo, scope.settings, scope.queue]),
      builder: (context, _) {
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

        // 問題回報 #941: with a camera, the 拍照 tab looks like a phone's own
        // camera — the live view fills the screen, the controls float on it.
        final controller = _controller;
        if (controller != null) {
          // Only a problem gets a line above the preview; otherwise nothing
          // is shown on the live view.
          final configured = scope.settings.taggingConfigured;
          final String? hint = !configured
              ? (TextScan.available ? '只找照片裡的{L}字・物品辨識未連線' : '照片辨識尚未連線')
              : scope.queue.offline
                  ? 'AI 離線 · 照片會先排隊'
                  : null;
          final photos = repo.photos;
          return _FullCamera(
            controller: controller,
            hint: hint,
            onHintTap: !configured
                ? () => scope.navigator.selectTab(AppTab.settings)
                : null,
            busy: _busy,
            flashing: _flashing,
            lastPhoto: photos.isEmpty ? null : photos.first,
            onGallery: _openPicker,
            onShutter: _capture,
            onFlip: _flip,
          );
        }

        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
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
                        onTap: () => scope.navigator.selectTab(AppTab.settings),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: MSpace.xl),
                    child: Container(
                      decoration: MDecor.heroPhotoFrame(),
                      clipBehavior: Clip.hardEdge,
                      child: _Viewfinder(
                        controller: _controller,
                        cameraError: _cameraError,
                        badge: badge,
                        onBadgeTap: _controller != null &&
                                !_busy &&
                                !scope.settings.taggingConfigured
                            ? () => scope.navigator.selectTab(AppTab.settings)
                            : null,
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
                                        ? MColors.primary.withValues(alpha: 0.6)
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
                                  icon: const MSvg(MIcon.settings20, size: 16),
                                  label: const UiText('設定辨識'),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Figma viewfinder (11:18): 24px corners, the AI badge top-left.
class _Viewfinder extends StatelessWidget {
  final CameraController? controller;
  final String? cameraError;
  final String badge;

  /// Recognition not set up: the badge opens 設定 → 照片辨識.
  final VoidCallback? onBadgeTap;

  const _Viewfinder({
    required this.controller,
    required this.cameraError,
    required this.badge,
    this.onBadgeTap,
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
    } else {
      // Camera starting or unavailable: an empty frame, not the last photo
      // (問題回報 #727); the badge and the notice below say what's going on.
      content = const ColoredBox(color: MColors.surfaceSoft);
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
                  '你可以按下方「選擇照片」，開始學單字。',
                  style: MFont.manrope(12, FontWeight.w600, MColors.ink),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// 問題回報 #1019 (card #848): the iPhone Camera layout — black all round,
/// a 3:4 live view between two black bands with nothing on it, and a solid
/// bottom band: latest photo (opens the picker), the shutter, flip camera.
/// A one-line hint above the view shows only when something is wrong.
class _FullCamera extends StatefulWidget {
  final CameraController controller;
  final String? hint;
  final VoidCallback? onHintTap;
  final bool busy;
  final bool flashing;
  final Photo? lastPhoto;
  final VoidCallback onGallery;
  final VoidCallback onShutter;
  final VoidCallback onFlip;

  const _FullCamera({
    required this.controller,
    required this.hint,
    required this.onHintTap,
    required this.busy,
    required this.flashing,
    required this.lastPhoto,
    required this.onGallery,
    required this.onShutter,
    required this.onFlip,
  });

  @override
  State<_FullCamera> createState() => _FullCameraState();
}

class _FullCameraState extends State<_FullCamera> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final hint = widget.hint;
    Widget preview = const SizedBox.shrink();
    if (c.value.isInitialized) {
      final size = c.value.previewSize;
      final w = size == null ? 300.0 : math.min(size.width, size.height);
      final h = size == null ? 400.0 : math.max(size.width, size.height);
      preview = FittedBox(
        fit: BoxFit.cover,
        clipBehavior: Clip.hardEdge,
        child: SizedBox(width: w, height: h, child: CameraPreview(c)),
      );
    }
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            SizedBox(
              height: 32,
              child: hint == null
                  ? null
                  : Center(
                      child: Tap(
                        onTap: widget.onHintTap,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Flexible(
                              child: UiText(hint,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: MFont.manrope(
                                      12, FontWeight.w700, Colors.white70)),
                            ),
                            if (widget.onHintTap != null)
                              const Icon(Icons.chevron_right_rounded,
                                  size: 14, color: Colors.white70),
                          ],
                        ),
                      ),
                    ),
            ),
            Expanded(
              child: Center(
                child: AspectRatio(
                  aspectRatio: 3 / 4,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      ClipRect(child: preview),
                      IgnorePointer(
                        child: AnimatedOpacity(
                          opacity: widget.flashing ? 1 : 0,
                          duration:
                              Duration(milliseconds: widget.flashing ? 0 : 200),
                          child: const ColoredBox(color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            Container(
              key: const ValueKey('camera-bottom-band'),
              color: Colors.black,
              padding: const EdgeInsets.fromLTRB(
                  MSpace.xl, MSpace.lg, MSpace.xl, MSpace.lg),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Tap(
                    onTap: widget.onGallery,
                    label: '最近一張照片',
                    child: Container(
                      key: const ValueKey('camera-last-photo'),
                      width: 48,
                      height: 48,
                      clipBehavior: Clip.antiAlias,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        color: Colors.white.withValues(alpha: 0.16),
                      ),
                      child: widget.lastPhoto != null
                          ? PhotoImage(widget.lastPhoto!, fit: BoxFit.cover)
                          : const Center(
                              child: MSvg(MIcon.gallery20,
                                  size: 22, tint: Colors.white)),
                    ),
                  ),
                  Listener(
                    onPointerDown: (_) => setState(() => _pressed = true),
                    onPointerUp: (_) => setState(() => _pressed = false),
                    onPointerCancel: (_) => setState(() => _pressed = false),
                    child: Tap(
                      onTap: widget.onShutter,
                      label: '拍照',
                      child: Container(
                        key: const ValueKey('camera-shutter'),
                        width: 76,
                        height: 76,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 4),
                        ),
                        padding: const EdgeInsets.all(4),
                        child: AnimatedScale(
                          scale: _pressed ? 0.88 : 1,
                          duration: const Duration(milliseconds: 100),
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: widget.busy
                                  ? Colors.white.withValues(alpha: 0.5)
                                  : Colors.white,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Tap(
                    onTap: widget.onFlip,
                    label: '切換鏡頭',
                    child: Container(
                      key: const ValueKey('camera-flip'),
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white.withValues(alpha: 0.16),
                      ),
                      child: const Icon(Icons.flip_camera_ios_outlined,
                          size: 24, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
