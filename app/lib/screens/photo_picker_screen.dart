import '../l10n/ui_text.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart'
    show MissingPluginException, Uint8List, rootBundle;
import 'package:image_picker/image_picker.dart';
import 'package:photo_manager/photo_manager.dart';

import '../app/app_scope.dart';
import '../models/photo.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';

/// Bundled sample images offered under 最近相片 until the user picks
/// their own (the mock's thumbnails).
const sampleRecentPhotos = [
  'assets/sample/recent_pasta.jpg',
  'assets/sample/recent_1.jpg',
  'assets/sample/recent_2.jpg',
  'assets/sample/recent_3.jpg',
  'assets/sample/recent_4.jpg',
  'assets/sample/recent_5.jpg',
  'assets/sample/recent_6.jpg',
];

class _Candidate {
  final String? asset;
  final Uint8List? bytes;
  final AssetEntity? entity;

  const _Candidate.asset(String this.asset)
      : bytes = null,
        entity = null;
  const _Candidate.bytes(Uint8List this.bytes)
      : asset = null,
        entity = null;
  const _Candidate.device(AssetEntity this.entity, Uint8List thumbnail)
      : asset = null,
        bytes = thumbnail;

  ImageProvider get image =>
      asset != null ? AssetImage(asset!) as ImageProvider : MemoryImage(bytes!);

  /// Longest edge kept for a device photo (same cap as the gallery picker).
  /// A 48MP original decodes to ~190 MB of pixels — several in a row used to
  /// take the app past the iOS memory limit (問題回報 #413).
  static const maxEdge = 2048;

  static Future<Uint8List?> _loadDevice(AssetEntity e) async {
    final longest = e.width > e.height ? e.width : e.height;
    if (longest <= maxEdge) return e.originBytes;
    // A box, not an exact size: it keeps the aspect ratio whatever the EXIF
    // orientation. iOS must be told to fit, its default fills and crops.
    // No fallback to originBytes here — that read is what crashed (#415).
    const box = ThumbnailSize.square(maxEdge);
    final option = defaultTargetPlatform == TargetPlatform.iOS
        ? ThumbnailOption.ios(
            size: box,
            quality: 90,
            resizeContentMode: ResizeContentMode.fit)
        : const ThumbnailOption(size: box, quality: 90);
    return e.thumbnailDataWithOption(option);
  }

  Future<Uint8List> load() async {
    if (entity != null) return await _loadDevice(entity!) ?? bytes!;
    return bytes ?? (await rootBundle.load(asset!)).buffer.asUint8List();
  }
}

/// 選擇照片 — Figma photo-picker-page (17:87): a big preview, a strip of
/// recent photos, and 從相簿選擇. 完成 saves the photo to a 相片冊 and
/// opens it for AI tagging — the spec's core loop, steps 1–2.
///
/// On Android and iOS, 最近相片 reads the device library after permission.
/// The web keeps the file-picker plus bundled samples as its fallback.
class PhotoPickerScreen extends StatefulWidget {
  /// Album to preselect in the save dialog.
  final String? albumId;

  const PhotoPickerScreen({super.key, this.albumId});

  @override
  State<PhotoPickerScreen> createState() => _PhotoPickerScreenState();
}

class _PhotoPickerScreenState extends State<PhotoPickerScreen> {
  static final _sessionPicks = <_Candidate>[];

  late final List<_Candidate> _candidates = [
    ..._sessionPicks,
    for (final a in sampleRecentPhotos) _Candidate.asset(a),
  ];
  int _selected = 0;
  bool _saving = false;
  bool _loadingDevice = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadDevicePhotos());
  }

  Future<void> _loadDevicePhotos() async {
    if (kIsWeb ||
        (defaultTargetPlatform != TargetPlatform.android &&
            defaultTargetPlatform != TargetPlatform.iOS)) {
      return;
    }
    setState(() => _loadingDevice = true);
    try {
      final permission = await PhotoManager.requestPermissionExtend(
          requestOption: const PermissionRequestOption(
              androidPermission: AndroidPermission(
                  type: RequestType.image, mediaLocation: false)));
      if (!permission.hasAccess) return;
      final albums = await PhotoManager.getAssetPathList(
          type: RequestType.image, onlyAll: true);
      if (albums.isEmpty) return;
      final entities = await albums.first.getAssetListPaged(page: 0, size: 30);
      // Thumbnails used to be read one by one: on iOS the first read of each
      // asset is slow (14 s for 19 photos, 問題回報 #416). Read a few at a
      // time and show every batch as soon as it is ready.
      const batch = 6;
      var shown = 0;
      for (var i = 0; i < entities.length; i += batch) {
        final chunk = entities.skip(i).take(batch);
        final thumbs = await Future.wait(chunk.map((e) => e
            .thumbnailDataWithSize(const ThumbnailSize.square(360),
                quality: 85)
            .catchError((_) => null)));
        if (!mounted) return;
        final device = <_Candidate>[
          for (var j = 0; j < thumbs.length; j++)
            if (thumbs[j] != null)
              _Candidate.device(chunk.elementAt(j), thumbs[j]!),
        ];
        if (device.isEmpty) continue;
        setState(() {
          _candidates.insertAll(shown, device);
          if (shown == 0) _selected = 0;
          shown += device.length;
          _loadingDevice = false;
        });
      }
    } on MissingPluginException {
      // Desktop tests and unsupported platforms keep the file picker.
    } catch (e) {
      debugPrint('Unable to load recent device photos: $e');
    } finally {
      if (mounted) setState(() => _loadingDevice = false);
    }
  }

  Future<void> _pickFromLibrary() async {
    try {
      final file = await ImagePicker()
          .pickImage(source: ImageSource.gallery, maxWidth: 2048);
      if (file == null || !mounted) return;
      final pick = _Candidate.bytes(await file.readAsBytes());
      _sessionPicks.insert(0, pick);
      setState(() {
        _candidates.insert(0, pick);
        _selected = 0;
      });
    } catch (e) {
      if (mounted) showToast(context, photoErrorMessage(e));
    }
  }

  Future<void> _done() async {
    if (_candidates.isEmpty || _saving) return;
    final scope = AppScope.of(context);
    final now = scope.clock();
    final Uint8List bytes;
    try {
      bytes = await _candidates[_selected].load();
    } catch (e) {
      if (mounted) showToast(context, photoErrorMessage(e));
      return;
    }
    if (!mounted) return;
    // The same picture again (spec §7 deferred this; card #217): offer the
    // existing photo instead of a second copy, but let the learner insist.
    Photo? existing;
    try {
      existing = scope.intake.findDuplicate(bytes);
    } catch (e) {
      debugPrint('duplicate check failed: $e');
    }
    if (existing != null) {
      final again = await showDuplicatePhotoDialog(context,
          existing: existing, repository: scope.repository);
      if (again == null || !mounted) return;
      if (!again) {
        Navigator.of(context).pop();
        scope.navigator.openPhoto(existing.id);
        return;
      }
    }
    final choice = await showSaveToAlbumDialog(
      context,
      repository: scope.repository,
      defaultTitle: defaultPhotoTitle(now),
      albumId: widget.albumId,
    );
    if (choice == null || !mounted) return;
    setState(() => _saving = true);
    try {
      final Photo photo = await scope.intake.addPhoto(
        bytes,
        title: choice.title,
        albumId: choice.albumId,
        scanMode: choice.scanMode,
      );
      unawaited(scope.queue.process());
      if (!mounted) return;
      Navigator.of(context).pop();
      scope.navigator.openPhoto(photo.id);
    } catch (e) {
      if (mounted) showToast(context, photoErrorMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = _candidates.isEmpty ? null : _candidates[_selected];
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            SizedBox(
              height: 72,
              child: AlbumTopBar(
                title: '選擇照片',
                leading: RoundIconButton(
                  label: '關閉',
                  icon: const MSvg(MIcon.xCircle, size: 20),
                  onTap: () => Navigator.of(context).maybePop(),
                ),
                trailing: Tap(
                  onTap: _saving ? null : _done,
                  label: '完成',
                  child: Container(
                    height: 40,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    alignment: Alignment.center,
                    child: _saving
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : UiText('完成',
                            style: MFont.inter(
                                16, FontWeight.w700, MColors.primary)),
                  ),
                ),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.only(top: 24, bottom: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Container(
                        height: 280,
                        clipBehavior: Clip.antiAlias,
                        decoration: BoxDecoration(
                          border: Border.all(color: MColors.hairline),
                          borderRadius: MRadii.rXl,
                          boxShadow: MShadows.card,
                        ),
                        child: selected == null
                            ? const SizedBox.shrink()
                            : Image(image: selected.image, fit: BoxFit.cover),
                      ),
                    ),
                    const SizedBox(height: 38),
                    Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                      child: Row(
                        children: [
                          Expanded(
                            child: UiText(
                                _loadingDevice
                                    ? '正在讀取最近照片…'
                                    : _candidates.length > sampleRecentPhotos.length
                                        ? '最近照片'
                                        : _sessionPicks.isEmpty
                                            ? '範例照片'
                                            : '已選照片與範例',
                                style: MFont.inter(
                                    14, FontWeight.w700, MColors.albumInk)),
                          ),
                          UiText('${_candidates.length} 張',
                              style: MFont.inter(
                                  13, FontWeight.w500, MColors.albumMuted)),
                        ],
                      ),
                    ),
                    SizedBox(
                      height: 68,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 4),
                        itemCount: _candidates.length,
                        separatorBuilder: (_, __) => const SizedBox(width: 10),
                        itemBuilder: (context, i) => Tap(
                          onTap: () => setState(() => _selected = i),
                          label: '相片 ${i + 1}',
                          child: Container(
                            width: 60,
                            height: 60,
                            clipBehavior: Clip.antiAlias,
                            decoration: BoxDecoration(
                              borderRadius: MRadii.rSm,
                              border: i == _selected
                                  ? Border.all(color: MColors.primary, width: 3)
                                  : null,
                            ),
                            child: Image(
                                image: _candidates[i].image, fit: BoxFit.cover),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 54),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Tap(
                        onTap: _pickFromLibrary,
                        label: '從相簿選擇',
                        child: Container(
                          height: 52,
                          decoration: BoxDecoration(
                            color: MColors.surface,
                            border:
                                Border.all(color: MColors.primary, width: 1.5),
                            borderRadius: BorderRadius.circular(26),
                            boxShadow: MShadows.soft,
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const MSvg(MIcon.galleryBlue, size: 18),
                              const SizedBox(width: 8),
                              UiText('從相簿選擇',
                                  style: MFont.inter(
                                      14, FontWeight.w700, MColors.primary)),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
