import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:image_picker/image_picker.dart';

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

  const _Candidate.asset(String this.asset) : bytes = null;
  const _Candidate.bytes(Uint8List this.bytes) : asset = null;

  ImageProvider get image =>
      asset != null ? AssetImage(asset!) as ImageProvider : MemoryImage(bytes!);

  Future<Uint8List> load() async =>
      bytes ?? (await rootBundle.load(asset!)).buffer.asUint8List();
}

/// 選擇照片 — Figma photo-picker-page (17:87): a big preview, a strip of
/// recent photos, and 從相簿選擇. 完成 saves the photo to a 相片冊 and
/// opens it for AI tagging — the spec's core loop, steps 1–2.
///
/// On a phone, 最近相片 would list the device's photo library; the web
/// can't read that, so the strip offers the bundled sample photos plus
/// whatever was picked with 從相簿選擇 this session.
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
      if (mounted) showToast(context, '無法開啟相簿：$e');
    }
  }

  Future<void> _done() async {
    if (_candidates.isEmpty || _saving) return;
    final scope = AppScope.of(context);
    final now = scope.clock();
    final choice = await showSaveToAlbumDialog(
      context,
      repository: scope.repository,
      defaultTitle: '新照片 ${now.month}/${now.day}',
      albumId: widget.albumId,
    );
    if (choice == null || !mounted) return;
    setState(() => _saving = true);
    try {
      final bytes = await _candidates[_selected].load();
      final Photo photo = await scope.intake.addPhoto(
        bytes,
        title: choice.title,
        albumId: choice.albumId,
      );
      unawaited(scope.queue.process());
      if (!mounted) return;
      Navigator.of(context).pop();
      scope.navigator.openPhoto(photo.id);
    } catch (e) {
      if (mounted) showToast(context, '儲存照片失敗：$e');
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
              height: 64,
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
                        : Text('完成',
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
                            child: Text(
                                _sessionPicks.isEmpty ? '範例照片' : '已選照片與範例',
                                style: MFont.inter(
                                    14, FontWeight.w700, MColors.albumInk)),
                          ),
                          Text('${_candidates.length} 張',
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
                              Text('從相簿選擇',
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
