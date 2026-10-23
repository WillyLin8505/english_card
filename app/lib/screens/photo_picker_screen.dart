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

  /// Decoded at a display size, never the full picture: a strip of picked
  /// 2048px photos decoded whole is 12 MB each (問題回報 #677, jetsam #413).
  ImageProvider sized(int width) =>
      ResizeImage.resizeIfNeeded(width, null, image);

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
///
/// Several photos can be ticked and added at once (問題回報 #677): the
/// album is asked once, they are saved one by one, and the tagging queue
/// recognizes them one at a time.
class PhotoPickerScreen extends StatefulWidget {
  /// Album to preselect in the save dialog.
  final String? albumId;

  /// 從相簿選擇: the system multi-photo picker; tests pass a fake.
  final Future<List<XFile>> Function()? pickLibrary;

  const PhotoPickerScreen({super.key, this.albumId, this.pickLibrary});

  @override
  State<PhotoPickerScreen> createState() => _PhotoPickerScreenState();
}

class _PhotoPickerScreenState extends State<PhotoPickerScreen> {
  static final _sessionPicks = <_Candidate>[];

  late final List<_Candidate> _candidates = [
    ..._sessionPicks,
    for (final a in sampleRecentPhotos) _Candidate.asset(a),
  ];

  /// The big preview; the newest candidate until one is tapped.
  _Candidate? _preview;

  /// Ticked photos, in tap order (問題回報 #677).
  final _chosen = <_Candidate>[];

  /// Which photo of a multi-photo add is being saved (1-based), or 0.
  int _progress = 0;
  bool _saving = false;
  bool _loadingDevice = false;

  /// Library picks kept for the session (they show again next time); capped
  /// so many picks don't pile up in memory.
  static const _maxSessionPicks = 30;

  _Candidate? get _shown => _preview ?? _candidates.firstOrNull;

  /// What 完成 adds: the ticked photos, or the previewed one.
  List<_Candidate> get _picks =>
      _chosen.isNotEmpty ? List.of(_chosen) : [if (_shown case final c?) c];

  void _toggle(_Candidate c) => setState(() {
        if (_chosen.remove(c)) {
          if (_preview == c) _preview = _chosen.lastOrNull ?? c;
        } else {
          _chosen.add(c);
          _preview = c;
        }
      });

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

  static Future<List<XFile>> _systemPicker() =>
      ImagePicker().pickMultiImage(maxWidth: 2048, limit: _maxSessionPicks);

  Future<void> _pickFromLibrary() async {
    try {
      final files = await (widget.pickLibrary ?? _systemPicker)();
      if (files.isEmpty || !mounted) return;
      // One file at a time: each is already scaled to 2048px by the picker.
      final picks = <_Candidate>[];
      for (final file in files) {
        picks.add(_Candidate.bytes(await file.readAsBytes()));
      }
      if (!mounted) return;
      _sessionPicks.insertAll(0, picks);
      if (_sessionPicks.length > _maxSessionPicks) {
        _sessionPicks.removeRange(_maxSessionPicks, _sessionPicks.length);
      }
      setState(() {
        _candidates.insertAll(0, picks);
        _chosen.addAll(picks);
        _preview = picks.first;
      });
    } catch (e) {
      if (mounted) showToast(context, photoErrorMessage(e));
    }
  }

  Future<void> _done() async {
    final picks = _picks;
    if (picks.isEmpty || _saving) return;
    if (picks.length == 1) return _addOne(picks.single);
    return _addMany(picks);
  }

  /// Several photos (問題回報 #677): one 存到相片冊 question for all, then
  /// each is read, checked for a duplicate and saved before the next one is
  /// read — never all originals in memory at once. Tagging starts after, and
  /// the queue takes them one at a time.
  Future<void> _addMany(List<_Candidate> picks) async {
    final scope = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final choice = await showSaveToAlbumDialog(
      context,
      repository: scope.repository,
      defaultTitle: defaultPhotoTitle(scope.clock()),
      albumId: widget.albumId,
      count: picks.length,
    );
    if (choice == null || !mounted) return;
    setState(() => _saving = true);
    var added = 0;
    var skipped = 0;
    Photo? openInstead;
    Object? error;
    try {
      for (var i = 0; i < picks.length; i++) {
        if (mounted) setState(() => _progress = i + 1);
        try {
          final bytes = await picks[i].load();
          Photo? existing;
          try {
            existing = scope.intake.findDuplicate(bytes);
          } catch (e) {
            debugPrint('duplicate check failed: $e');
          }
          if (existing != null) {
            // The same rule as one photo: ask. In a batch, 打開原本的照片
            // (or dismissing) skips this one and the rest go on.
            final again = mounted
                ? await showDuplicatePhotoDialog(context,
                    existing: existing, repository: scope.repository)
                : null;
            if (again != true) {
              skipped++;
              if (again == false) openInstead = existing;
              continue;
            }
          }
          await scope.intake.addPhoto(
            bytes,
            title: choice.title,
            albumId: choice.albumId,
            scanMode: choice.scanMode,
          );
          added++;
        } catch (e) {
          debugPrint('Adding photo ${i + 1}/${picks.length} failed: $e');
          error = e;
        }
      }
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
          _progress = 0;
        });
      }
    }
    if (added > 0) unawaited(scope.queue.process());
    if (!mounted) return;
    if (added == 0) {
      if (openInstead != null) {
        Navigator.of(context).pop();
        scope.navigator.openPhoto(openInstead.id);
      } else if (error != null) {
        showToast(context, photoErrorMessage(error));
      }
      return;
    }
    Navigator.of(context).pop();
    scope.navigator.selectTab(AppTab.album);
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
          content: UiText(skipped == 0
              ? '已加入 $added 張照片，AI 會一張一張辨識'
              : '已加入 $added 張照片，AI 會一張一張辨識（$skipped 張已加入過，略過）')));
  }

  Future<void> _addOne(_Candidate pick) async {
    final scope = AppScope.of(context);
    final now = scope.clock();
    final Uint8List bytes;
    try {
      bytes = await pick.load();
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
    final selected = _shown;
    final count = _chosen.length;
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
                  label: count > 1 ? '加入 $count 張' : '完成',
                  child: Container(
                    height: 40,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    alignment: Alignment.center,
                    child: _saving
                        ? Row(mainAxisSize: MainAxisSize.min, children: [
                            const SizedBox.square(
                                dimension: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2)),
                            if (_progress > 0 && count > 1) ...[
                              const SizedBox(width: 6),
                              Text('$_progress/$count',
                                  style: MFont.inter(
                                      13, FontWeight.w600, MColors.primary)),
                            ],
                          ])
                        : UiText(count > 1 ? '加入 $count 張' : '完成',
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
                            : Image(
                                image: selected.sized(1200), fit: BoxFit.cover),
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
                          UiText(
                              count > 0
                                  ? '已選 $count 張'
                                  : '${_candidates.length} 張',
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
                        itemBuilder: (context, i) => _Thumb(
                          candidate: _candidates[i],
                          index: i,
                          previewed: _candidates[i] == selected,
                          order: _chosen.indexOf(_candidates[i]) + 1,
                          onTap: _saving ? null : () => _toggle(_candidates[i]),
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

/// One 最近照片 thumbnail: tap to tick it; ticked ones show their order
/// (問題回報 #677).
class _Thumb extends StatelessWidget {
  final _Candidate candidate;
  final int index;
  final bool previewed;

  /// 1-based place among the ticked photos, 0 when not ticked.
  final int order;
  final VoidCallback? onTap;

  const _Thumb({
    required this.candidate,
    required this.index,
    required this.previewed,
    required this.order,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final ticked = order > 0;
    return Tap(
      onTap: onTap,
      label: ticked ? '相片 ${index + 1}（已選）' : '相片 ${index + 1}',
      child: SizedBox(
        width: 60,
        height: 60,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Container(
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                borderRadius: MRadii.rSm,
                border: ticked || previewed
                    ? Border.all(
                        color: ticked ? MColors.primary : MColors.hairline,
                        width: 3)
                    : null,
              ),
              child: Image(image: candidate.sized(180), fit: BoxFit.cover),
            ),
            if (ticked)
              Positioned(
                top: 3,
                right: 3,
                child: Container(
                  width: 20,
                  height: 20,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: MColors.primary,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 1.5),
                  ),
                  child: Text('$order',
                      style: MFont.inter(11, FontWeight.w700, Colors.white)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
